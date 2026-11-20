"""KIPRIS Plus 특허 출원 수 수집기 (3주차).

하는 일
1. config/keywords.csv의 kipris_keywords(특허 검색어, | 로 구분)를 읽는다.
2. 검색어마다 KIPRIS Plus 'getAdvancedSearch'로 '요약(astrtCont)에 그 단어가 들어간'
   특허·실용신안을 한 번에 500건씩 모두 받는다.
3. 한 성분 안에서 같은 특허(출원번호)는 한 번만 남긴다.
4. 원본 목록은 data/raw/kipris_items_<날짜>.csv, 월별 출원 수는 data/raw/kipris_<날짜>.csv로 저장한다.
   월별 출원 수는 두 가지로 센다.
     - kipris_all:      검색된 모든 특허
     - kipris_cosmetic: IPC 분류가 화장품(A61K 8/, A61Q)인 특허만

특별 규칙
  - PLANT_PDRN: 이름으로는 거의 검색되지 않아서, PDRN 특허 중 제목·요약에
    "OO 유래 PDRN", "OO으로부터 추출한 DNA"처럼 출처가 식물(해조류 포함)인 표현이 있는 것을
    식물성 PDRN으로 본다. 미생물(유산균·효모) 유래는 식물성에 넣지 않는다.
  - NIACINAMIDE: '니코틴아미드'로 검색하면 NMN(니코틴아미드 모노뉴클레오티드) 같은
    먹는 노화방지 성분 특허가 섞이므로, 나이아신아마이드 표기 없이 NMN·NR만 언급한 특허는 뺀다.

주의
  - 특허는 출원 후 약 18개월이 지나야 공개된다. 그래서 최근 약 1년 반의 출원 수는
    실제보다 적게 나온다(분석 때 따로 표시).
  - 무료 이용은 월 1,000회 호출. 검색어별 결과를 data/raw/kipris_cache/에 저장해 두고,
    다시 실행하면 이미 받은 검색어는 호출하지 않는다.

실행 예
    python src/collect_kipris.py --dry-run        # 검색어별 특허 수와 필요한 호출 수만 확인
    python src/collect_kipris.py --only PDRN      # 한 성분만
    python src/collect_kipris.py                  # 전체
"""
import argparse
import math
import os
import re
import time

import pandas as pd
import requests
from dotenv import load_dotenv

from common import ROOT, RAW_DIR, raw_path

API_URL = "http://plus.kipris.or.kr/kipo-api/kipi/patUtiModInfoSearchSevice/getAdvancedSearch"
PAGE_SIZE = 500          # 한 번에 받을 수 있는 최대 건수
SLEEP_SEC = 1.0          # 너무 빨리 부르면 서버가 연결을 끊어서 1초씩 쉰다
CACHE_DIR = RAW_DIR / "kipris_cache"
FIELDS = ["applicationNumber", "applicationDate", "openDate", "registerStatus",
          "ipcNumber", "inventionTitle", "applicantName", "astrtCont"]
COSMETIC_IPC = re.compile(r"(^|\|)\s*(A61K 8/|A61Q)")


def is_cosmetic(ipc):
    """A61K 8/ 또는 A61Q가 있으면 화장품 특허. 단 A61Q 중 11(치약·구강용)만 있으면 제외.
    [검수 11/20] 쑥 '화장품IPC' 표본의 X 5건 중 4건이 치약·구취 제품이었다
    (구강용품도 A61K 8/ + A61Q 11로 분류되기 때문)."""
    ipc = str(ipc or "")
    if not COSMETIC_IPC.search(ipc):
        return False
    q = [c.strip() for c in ipc.split("|") if c.strip().startswith("A61Q")]
    return not (q and all(c.startswith("A61Q 11") for c in q))

# 식물성 PDRN 판단: 단어가 있는지만 보면 '줄기세포', '피부 홍조', '동백꽃 추출물 함유' 같은
# 엉뚱한 특허가 걸린다. 그래서 "OO 유래 PDRN", "OO으로부터 추출한 DNA"처럼
# PDRN의 출처를 말하는 표현을 찾고, 출처(OO)가 동물·세포·미생물이 아니면 식물성으로 본다.
NUC = r"(?:PDRN|피디알엔|폴리\s?데옥시|폴리\s?디옥시|DNA|유전자)"
PLANT_SOURCE = re.compile(
    r"([가-힣]{1,10})\s*(?:세포\s*)?(?:캘러스\s*)?"
    r"(?:유래(?:의|된|한)?|으로부터|로부터|에서\s*유래(?:된|한)?|에서\s*추출(?:된|한)?)\s*"
    r"(?:정제\s*|분리(?:된|한)?\s*)?(?:추출(?:된|한)?\s*)?(?:[가-힣]+\s+){0,3}?" + NUC)
PLANT_DIRECT = re.compile(r"(식물성|장미|대마 줄기)\s*" + NUC)
NOT_PLANT = ["연어", "송어", "산천어", "어류", "넙치", "상어", "불가사리", "해양생물", "정소", "정액",
             "정자", "수정란", "생식", "이리", "조직", "인체", "사람", "인간", "줄기", "골수", "지방",
             "편도", "동물", "태반", "돼지", "혈소판", "세포외", "엑소좀",
             "미생물", "균", "효모", "발효", "클론", "재조합", "합성", "생체",
             "침전물", "부산물", "히알루론산", "방법", "명세서", "발명", "기술", "단계", "조건",
             "갖는", "상기", "이로", "이의", "것"]


def plant_source(text):
    """PDRN의 출처가 식물(해조류 포함)이라고 말하는 표현을 찾아 돌려준다. 없으면 빈 문자열."""
    for m in PLANT_SOURCE.finditer(text):
        if not any(w in m.group(1) for w in NOT_PLANT):
            return m.group(0)[:40]
    m = PLANT_DIRECT.search(text)
    return m.group(0) if m else ""
NIACIN_WORDS = ["나이아신아마이드", "나이아신아미드", "니아신아미드"]
NMN_WORDS = ["모노뉴클레오티드", "모노뉴클레오타이드", "NMN", "리보사이드", "리보시드"]


def call_api(params, key, retries=4):
    """API를 부르고 XML 글자를 돌려준다. 연결이 끊기면 조금씩 더 오래 쉬고 다시 시도한다."""
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(API_URL, params={**params, "ServiceKey": key}, timeout=120)
            resp.raise_for_status()
            text = resp.text
            code = re.search(r"<resultCode>(.*?)</resultCode>", text)
            if code and code.group(1) not in ("00", ""):
                msg = re.search(r"<resultMsg>(.*?)</resultMsg>", text)
                raise RuntimeError(f"API 오류 {code.group(1)}: {msg.group(1) if msg else ''}")
            return text
        except requests.RequestException as e:
            if attempt == retries:
                raise
            print(f"\n  ! 연결 문제({type(e).__name__}), {5 * attempt}초 후 다시 시도")
            time.sleep(5 * attempt)


def parse_items(xml):
    rows = []
    for item in re.findall(r"<item>(.*?)</item>", xml, re.S):
        row = {}
        for f in FIELDS:
            m = re.search(fr"<{f}>(.*?)</{f}>", item, re.S)
            row[f] = m.group(1).strip() if m else ""
        rows.append(row)
    return rows


def total_count(term, key):
    xml = call_api({"astrtCont": term, "patent": "true", "utility": "true",
                    "numOfRows": "1", "pageNo": "1"}, key)
    m = re.search(r"<totalCount>(\d+)", xml)
    return int(m.group(1)) if m else 0


def fetch_term(term, key):
    """검색어 하나의 특허를 모두 받는다. 이미 받은 적 있으면 저장본을 쓴다."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w가-힣]+", "_", term)
    cache = CACHE_DIR / f"{safe}.csv"
    if cache.exists():
        return pd.read_csv(cache, dtype=str, keep_default_na=False), 0

    rows, page, total, calls = [], 1, None, 0
    while True:
        xml = call_api({"astrtCont": term, "patent": "true", "utility": "true",
                        "numOfRows": str(PAGE_SIZE), "pageNo": str(page)}, key)
        calls += 1
        time.sleep(SLEEP_SEC)
        if total is None:
            m = re.search(r"<totalCount>(\d+)", xml)
            total = int(m.group(1)) if m else 0
        got = parse_items(xml)
        rows.extend(got)
        if not got or len(rows) >= total:
            break
        page += 1
    df = pd.DataFrame(rows, columns=FIELDS)
    df.to_csv(cache, index=False, encoding="utf-8-sig")
    return df, calls


def has_any(text, words):
    return any(w in text for w in words)


def main():
    parser = argparse.ArgumentParser(description="KIPRIS 특허 출원 수 수집")
    parser.add_argument("--only", nargs="*", help="특정 성분만 (예: --only PDRN CICA)")
    parser.add_argument("--start", default="2010-01", help="월별 집계 시작 월")
    parser.add_argument("--dry-run", action="store_true", help="검색어별 특허 수와 필요한 호출 수만 출력")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    key = (os.getenv("KIPRIS_API_KEY") or "").strip()
    if not key:
        raise SystemExit(".env에 KIPRIS_API_KEY가 없습니다.")

    kw = pd.read_csv(ROOT / "config" / "keywords.csv", encoding="utf-8-sig", dtype=str, keep_default_na=False)
    if args.only:
        need = set(args.only) | ({"PDRN"} if "PLANT_PDRN" in args.only else set())
        kw = kw[kw["ingredient_id"].isin(need)]
    searchable = kw[kw["ingredient_id"] != "PLANT_PDRN"]

    if args.dry_run:
        calls = 0
        for r in searchable.itertuples():
            parts = []
            for term in r.kipris_keywords.split("|"):
                n = total_count(term, key)
                time.sleep(SLEEP_SEC)
                calls += max(1, math.ceil(n / PAGE_SIZE))
                parts.append(f"{term}={n:,}")
            print(f"{r.ingredient_id:16s} " + " | ".join(parts))
        print(f"\n전체 수집에 필요한 호출: 최대 약 {calls}번 (이미 받은 검색어는 0번)")
        return

    all_items, used = [], 0
    for r in searchable.itertuples():
        frames = []
        for term in r.kipris_keywords.split("|"):
            df, calls = fetch_term(term, key)
            used += calls
            frames.append(df.assign(matched_term=term))
        items = pd.concat(frames, ignore_index=True)
        # 같은 특허가 여러 검색어에 걸리면 걸린 검색어를 모아 한 줄로 만든다
        terms = items.groupby("applicationNumber")["matched_term"].agg(lambda s: "|".join(dict.fromkeys(s)))
        items = items.drop_duplicates("applicationNumber").drop(columns="matched_term")
        items["matched_term"] = items["applicationNumber"].map(terms)
        items.insert(0, "ingredient_id", r.ingredient_id)

        if r.ingredient_id == "NIACINAMIDE":
            text = items["inventionTitle"] + " " + items["astrtCont"]
            nmn_only = text.map(lambda t: has_any(t, NMN_WORDS) and not has_any(t, NIACIN_WORDS))
            print(f"  NIACINAMIDE: NMN·NR만 언급한 특허 {nmn_only.sum()}건 제외")
            items = items[~nmn_only]
        all_items.append(items)
        print(f"{r.ingredient_id:16s} 특허 {len(items):>6,}건")

        if r.ingredient_id == "PDRN" and (not args.only or "PLANT_PDRN" in args.only):
            source = (items["inventionTitle"] + " " + items["astrtCont"]).map(plant_source)
            plant = items[source != ""].copy()
            plant["ingredient_id"] = "PLANT_PDRN"
            plant["matched_term"] = "PDRN 중 식물 출처: " + source[source != ""]
            all_items.append(plant)
            print(f"{'PLANT_PDRN':16s} 특허 {len(plant):>6,}건 (PDRN 중 출처가 식물·해조류)")

    items = pd.concat(all_items, ignore_index=True)
    if args.only:
        items = items[items["ingredient_id"].isin(args.only)]
    items["is_cosmetic_ipc"] = items["ipcNumber"].map(is_cosmetic)
    items["month"] = pd.to_datetime(items["applicationDate"], format="%Y%m%d", errors="coerce").dt.to_period("M")

    items_path = raw_path("kipris_items")
    items.drop(columns="month").to_csv(items_path, index=False, encoding="utf-8-sig")

    # 월별 출원 수 (특허가 없는 달은 0)
    months = pd.period_range(args.start, pd.Timestamp.today().to_period("M") - 1, freq="M")
    out = []
    for source, subset in [("kipris_all", items), ("kipris_cosmetic", items[items["is_cosmetic_ipc"]])]:
        counts = subset.groupby(["ingredient_id", "month"]).size()
        for ing in items["ingredient_id"].unique():
            for p in months:
                out.append({"ingredient_id": ing, "stage": "patent", "source": source,
                            "month": str(p), "value": int(counts.get((ing, p), 0)), "value_type": "count"})
    out = pd.DataFrame(out)
    csv_path = raw_path("kipris")
    out.to_csv(csv_path, index=False, encoding="utf-8-sig")

    summary = items.groupby("ingredient_id", sort=False).agg(
        all=("applicationNumber", "size"), cosmetic=("is_cosmetic_ipc", "sum"))
    summary["cosmetic_share"] = (summary["cosmetic"] / summary["all"]).round(2)
    print("\n" + summary.to_string())
    print(f"\n이번 실행 API 호출: {used}번")
    print(f"저장 완료: {items_path}\n          {csv_path}")


if __name__ == "__main__":
    main()
