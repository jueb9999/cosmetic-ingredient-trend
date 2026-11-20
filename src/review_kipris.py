"""KIPRIS 특허 필터 정확도 점검 도구 (3주차).

왜 필요한가
  collect_kipris.py는 성분 이름이 들어간 특허를 모은 뒤, IPC(국제특허분류)에
  'A61K 8/'(화장품 성분) 또는 'A61Q'(화장품 용도)가 있으면 '화장품 특허'로 센다.
  그런데 이 필터가 틀릴 수 있다.
    - 화장품 IPC인데 성분이 그냥 목록에 한 번 언급만 된 특허 (부풀려짐)
    - 피부·미용 특허인데 의약품(A61K 31/ 등) IPC만 달려 빠진 특허 (놓침)
  식물성 PDRN 판정(유래 표현 규칙)도 맞는지 사람이 확인해야 한다.
  그래서 2주차 PubMed처럼 무작위로 뽑아 O/X를 매기고 정확도를 잰다.

뽑는 방법 (seed 고정 -> 다시 실행해도 같은 특허)
  - 일반 성분: '화장품IPC' 10건 + '기타IPC' 5건
  - PLANT_PDRN: '식물판정'(식물성으로 분류된 PDRN) 15건
                + '비식물판정'(PDRN인데 식물로 안 잡힌 것) 5건

사용 순서
  1) python src/review_kipris.py
  2) data/review/kipris_review_<날짜>.csv를 엑셀로 열고, 각 줄의 question에 답해
     relevant 칸에 O / X / ?(애매, 계산 제외)를 적고 저장
  3) python src/review_kipris.py --summary data/review/kipris_review_<날짜>.csv

결과 해석
  화장품IPC의 O 비율  = 필터 정확도(높을수록 좋음)
  기타IPC의 O 비율    = 필터가 놓친 비율(낮을수록 좋음)
  -> 둘을 합쳐 '실제 화장품 특허 수'를 추정한다.

주의: 점검 파일에는 특허 요약문 일부가 들어가므로 GitHub에 올리지 않는다
      (.gitignore 처리). 정확도 요약 파일(kipris_precision_*.csv)만 올린다.
"""
import argparse
import glob
import random
import re

import pandas as pd

from collect_kipris import is_cosmetic
from common import load_keywords, today_tag, ROOT, RAW_DIR

REVIEW_DIR = ROOT / "data" / "review"

Q_COS = "이 성분을 실제로 쓰는 화장품·피부 미용 특허인가?"
Q_PLANT = "PDRN(DNA)을 식물(꽃·잎·캘러스 등)에서 얻는 특허인가?"


def latest_items():
    files = sorted(glob.glob(str(RAW_DIR / "kipris_items_*.csv")))
    if not files:
        raise SystemExit("data/raw/kipris_items_*.csv가 없어요. collect_kipris.py를 먼저 실행하세요.")
    return files[-1]


def snippet(text, terms, width=90):
    """요약문에서 검색어가 처음 나오는 곳 앞뒤만 잘라 보여준다."""
    text = re.sub(r"\s+", " ", str(text or ""))
    for t in terms:
        i = text.find(t)
        if i >= 0:
            s, e = max(0, i - width), min(len(text), i + len(t) + width)
            return ("…" if s else "") + text[s:e] + ("…" if e < len(text) else "")
    return text[: width * 2]


def make_review(args):
    items = pd.read_csv(latest_items(), dtype={"applicationNumber": str})
    kw = load_keywords().set_index("ingredient_id")
    rows = []

    def add(ing, group, df, n, question):
        df = df.sort_values("applicationNumber")
        idx = list(df.index)
        pick = random.Random(f"{args.seed}-{ing}-{group}").sample(idx, min(n, len(idx)))
        for k, i in enumerate(sorted(pick), 1):
            r = df.loc[i]
            terms = [t for t in str(r["matched_term"]).replace("PDRN 중 식물 출처: ", "").split("|") if t]
            if ing == "PLANT_PDRN" or group == "비식물판정":
                terms = terms + ["PDRN", "DNA", "폴리데옥시"]
            rows.append({
                "ingredient_id": ing,
                "name_ko": kw.loc[ing, "name_ko"] if ing in kw.index else ing,
                "group": group,
                "no": k,
                "question": question,
                "relevant": "",
                "memo": "",
                "title": r["inventionTitle"],
                "snippet": snippet(r["astrtCont"], terms),
                "matched_term": r["matched_term"],
                "ipc": r["ipcNumber"],
                "applicant": r["applicantName"],
                "year": str(r["applicationDate"])[:4],
                "applicationNumber": "KR" + str(r["applicationNumber"]),  # 글자로 저장해야 엑셀이 1.02E+12로 망가뜨리지 않음
                "group_total": len(df),
            })

    ings = args.only or [i for i in kw.index if i in set(items.ingredient_id)]
    for ing in ings:
        d = items[items.ingredient_id == ing]
        if ing == "PLANT_PDRN":
            add(ing, "식물판정", d, 15, Q_PLANT)
            plant_ids = set(d.applicationNumber)
            p = items[(items.ingredient_id == "PDRN") & ~items.applicationNumber.isin(plant_ids)]
            add(ing, "비식물판정", p, 5, Q_PLANT)
        else:
            add(ing, "화장품IPC", d[d.is_cosmetic_ipc], args.n_cos, Q_COS)
            add(ing, "기타IPC", d[~d.is_cosmetic_ipc], args.n_other, Q_COS)

    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    out = REVIEW_DIR / f"kipris_review_{today_tag()}.csv"
    k = 2
    while out.exists():
        out = REVIEW_DIR / f"kipris_review_{today_tag()}_{k}.csv"
        k += 1
    pd.DataFrame(rows).to_csv(out, index=False, encoding="utf-8-sig")
    print(f"저장: {out.relative_to(ROOT)}  ({len(rows)}건)")
    print("엑셀로 열어 relevant 칸에 O / X / ? 를 적고 저장하세요.")


def summarize(path):
    try:
        d = pd.read_csv(path, encoding="utf-8-sig", dtype=str)
    except UnicodeDecodeError:
        d = pd.read_csv(path, encoding="cp949", dtype=str)
    d["relevant"] = d["relevant"].fillna("").str.strip().str.upper()
    # 점검 후 필터 규칙이 바뀌었을 수 있으므로(예: 11/20 구강용품 제외) 현재 규칙으로 다시 나눈다.
    # 화장품IPC 표본 중 이제 화장품이 아닌 것은 기타IPC로 옮기고, 전체 건수도 최신 파일에서 다시 센다.
    d.loc[(d.group == "화장품IPC") & ~d["ipc"].map(is_cosmetic), "group"] = "기타IPC"
    items = pd.read_csv(latest_items(), dtype={"applicationNumber": str})
    items["is_cosmetic_ipc"] = items["ipcNumber"].map(is_cosmetic)
    plant_ids = set(items.loc[items.ingredient_id == "PLANT_PDRN", "applicationNumber"])
    totals = {}
    for ing, g in items.groupby("ingredient_id"):
        totals[(ing, "화장품IPC")] = int(g.is_cosmetic_ipc.sum())
        totals[(ing, "기타IPC")] = int((~g.is_cosmetic_ipc).sum())
    totals[("PLANT_PDRN", "식물판정")] = len(plant_ids)
    totals[("PLANT_PDRN", "비식물판정")] = int(((items.ingredient_id == "PDRN") & ~items.applicationNumber.isin(plant_ids)).sum())
    d["group_total"] = [totals.get((i, g), 0) for i, g in zip(d.ingredient_id, d.group)]
    rows = []
    for ing, g in d.groupby("ingredient_id", sort=False):
        rec = {"ingredient_id": ing}
        for grp, gg in g.groupby("group"):
            ox = gg[gg.relevant.isin(["O", "X"])]
            rec[f"{grp}_n"] = len(ox)
            rec[f"{grp}_O비율"] = round((ox.relevant == "O").mean(), 2) if len(ox) else None
            rec[f"{grp}_전체"] = gg.group_total.iloc[0]
        if ing == "PLANT_PDRN":
            prec = rec.get("식물판정_O비율")
            miss = rec.get("비식물판정_O비율") or 0
            if prec is not None:
                rec["추정_실제건수"] = round(rec["식물판정_전체"] * prec + rec.get("비식물판정_전체", 0) * miss)
        else:
            prec = rec.get("화장품IPC_O비율")
            miss = rec.get("기타IPC_O비율") or 0
            if prec is not None:
                rec["추정_실제건수"] = round(rec["화장품IPC_전체"] * prec + rec.get("기타IPC_전체", 0) * miss)
        if prec is None:
            rec["판정"] = "미입력"
        elif prec >= 0.8 and miss <= 0.2:
            rec["판정"] = "양호"
        elif prec >= 0.5:
            rec["판정"] = "다듬기 권장"
        else:
            rec["판정"] = "다듬기 필요"
        rows.append(rec)
    res = pd.DataFrame(rows)
    out = REVIEW_DIR / f"kipris_precision_{today_tag()}.csv"
    res.to_csv(out, index=False, encoding="utf-8-sig")
    pd.set_option("display.width", 200)
    print(res.to_string(index=False))
    print(f"\n저장: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="+")
    ap.add_argument("--n-cos", type=int, default=10)
    ap.add_argument("--n-other", type=int, default=5)
    ap.add_argument("--seed", default="2026")
    ap.add_argument("--summary")
    a = ap.parse_args()
    summarize(a.summary) if a.summary else make_review(a)
