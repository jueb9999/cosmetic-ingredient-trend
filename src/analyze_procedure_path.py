"""'시술 → 원료사 → 브랜드' 확산 경로 검증 (4주차 추가 분석).

가설 (로레알 인터뷰에서 들은 말)
  "피부과 시술이 뜨면 원료 회사가 움직이고, 브랜드가 움직인다."
  4주차 분석에서 PDRN은 '논문·특허 → 소비자'가 아니라 검색이 먼저였다.
  그렇다면 시술에서 출발하는 다른 경로가 있는지 단계별 시작 시점으로 확인한다.

단계와 측정 방법
  ① 시술 관심      : 네이버 시술 검색량 (리쥬란, 연어주사, 엑소좀시술, 백옥주사 등)
  ② 원료 회사      : 원료사(원료사·ODM 포함)가 낸 화장품 특허 수
  ③ 제조사(ODM)    : ODM이 낸 화장품 특허 수
  ④ 브랜드         : 브랜드사가 낸 화장품 특허 수
  ⑤ 소비자(화장품) : 네이버 화장품 검색량 (PDRN크림, 엑소좀앰플 등)
  * 출원인 분류는 config/applicant_types.csv (특허 많은 상위 기업, 혜우 검토)
  * 시술 경로와 비교하려고 시술과 관계없는 성분(나이아신아마이드, 시카, 레티놀)도 같이 계산한다.

시점 계산 (모든 단계에 같은 잣대, 같은 기간)
  - 기간: 2016-01 ~ 특허 공개가 끝난 달(현재 2025-04). 검색량도 같은 달에서 자른다.
    (기간이 다르면 '누적 몇 %' 시점이 달라져 비교가 틀어진다)
  - 기업 유형별 특허는 연 몇 건뿐이라 전년 대비 규칙이 흔들린다. 그래서 '누적 비율' 방식을 쓴다.
    1) 평소 수준(12개월 평균의 최솟값)을 뺀다. 백옥주사·보톡스처럼 원래 높던 검색은 '늘어난 만큼'만 남는다.
       특허는 평소 수준이 대부분 0이라 그대로다.
    2) 늘어난 양을 처음부터 더해 가며 전체의 25%(T25, 본격화), 50%(T50, 절정 무렵)에 도달한 달을 찾는다.
  - 특허는 5건 미만이면 판단하지 않는다(빈칸).

실행
  python src/analyze_procedure_path.py
  -> data/processed/procedure_path_yearly.csv  (단계별 연도 값)
     data/processed/procedure_path_onsets.csv  (단계별 시작 시점과 순서)
     data/processed/w4_procedure_path.png
"""
import glob

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from common import RAW_DIR, ROOT, load_keywords, use_korean_font

PROCESSED = ROOT / "data" / "processed"
PROCEDURE_INGS = ["PDRN", "EXOSOME", "SPICULE", "GLUTATHIONE", "PEPTIDE"]
CONTROL_INGS = ["NIACINAMIDE", "CICA", "RETINOL"]
TYPE_TO_STAGE = {"제약·시술": "시술 제품사 특허", "원료사": "원료사 특허", "원료사·ODM": "원료사 특허",
                 "ODM": "ODM 특허", "브랜드사": "브랜드사 특허"}
STAGES = ["시술 검색", "시술 제품사 특허", "원료사 특허", "ODM 특허", "브랜드사 특허", "화장품 검색"]
STAGE_EN = {"시술 검색": "Procedure search", "시술 제품사 특허": "Procedure-maker patents",
            "원료사 특허": "Ingredient-supplier patents", "ODM 특허": "ODM patents",
            "브랜드사 특허": "Brand patents", "화장품 검색": "Cosmetic search"}
COLOR = {"시술 검색": "#C44E52", "시술 제품사 특허": "#8172B3", "원료사 특허": "#DD8452",
         "ODM 특허": "#937860", "브랜드사 특허": "#4C72B0", "화장품 검색": "#55A868"}
START = "2016-01"
Q = 0.25


def patents_by_stage(cut):
    files = sorted(glob.glob(str(RAW_DIR / "kipris_items_*.csv")))
    if not files:
        raise SystemExit("data/raw/kipris_items_*.csv가 없어요. collect_kipris.py를 먼저 실행하세요.")
    items = pd.read_csv(files[-1], dtype=str)
    items = items[items["is_cosmetic_ipc"] == "True"]
    types = pd.read_csv(ROOT / "config" / "applicant_types.csv", encoding="utf-8-sig")
    tmap = dict(zip(types["applicant"].str.strip(), types["type"]))
    ap = items.assign(applicant=items["applicantName"].fillna("").str.split("|")).explode("applicant")
    ap["applicant"] = ap["applicant"].str.strip()
    ap["stage"] = ap["applicant"].map(tmap).map(TYPE_TO_STAGE)
    ap["month"] = ap["applicationDate"].str[:4] + "-" + ap["applicationDate"].str[4:6]
    ap = ap[(ap["month"] >= START) & (ap["month"] <= cut)]
    # 분류 비율: 성분별로 특허 중 단계가 정해진 특허 비율
    cover = ap.groupby(["ingredient_id", "applicationNumber"])["stage"].apply(lambda s: s.notna().any())
    coverage = cover.groupby("ingredient_id").mean().round(2)
    ap = ap.dropna(subset=["stage"]).drop_duplicates(["ingredient_id", "stage", "applicationNumber"])
    return ap, coverage


def monthly(values_by_month, cut):
    idx = pd.period_range(START, cut, freq="M")
    s = pd.Series(values_by_month, dtype=float)
    s.index = pd.PeriodIndex(s.index, freq="M")
    return s.groupby(level=0).sum().reindex(idx, fill_value=0.0)


def t_month(s, q):
    """평소 수준을 뺀 '늘어난 양'이 누적 q에 도달한 달."""
    base = s.rolling(12).mean().min()
    excess = (s - base).clip(lower=0)
    if excess.sum() <= 0:
        return None
    cum = excess.cumsum() / excess.sum()
    return str(cum.index[(cum >= q).argmax()])


def main():
    long = pd.read_csv(PROCESSED / "trend_long.csv", encoding="utf-8-sig")
    if "naver_procedure" not in set(long["source"]):
        raise SystemExit("trend_long.csv에 시술 검색량이 없어요. collect_naver.py --procedure 후 build_dataset.py를 실행하세요.")
    cut = long.loc[(long["stage"] == "patent") & ~long["provisional"], "month"].max()
    ap, coverage = patents_by_stage(cut)
    kw = load_keywords().set_index("ingredient_id")

    rows, yearly = [], []
    for ing in PROCEDURE_INGS + CONTROL_INGS:
        rec = {"ingredient_id": ing, "path_group": "시술 성분" if ing in PROCEDURE_INGS else "비교군(시술 없음)",
               "patent_coverage": coverage.get(ing)}
        for stage, src in [("시술 검색", "naver_procedure"), ("화장품 검색", "naver")]:
            g = long[(long["ingredient_id"] == ing) & (long["source"] == src)]
            if g.empty:
                continue
            s = monthly(dict(zip(g["month"], g["value"])), cut)
            rec[stage], rec[stage + "_T50"] = t_month(s, Q), t_month(s, 0.5)
            y = g.assign(year=g["month"].str[:4]).groupby("year")["value"].mean()
            yearly += [{"ingredient_id": ing, "stage": stage, "year": k, "value": round(v, 2)} for k, v in y.items()]
        for stage in STAGES[1:5]:
            months = ap[(ap["ingredient_id"] == ing) & (ap["stage"] == stage)]["month"].tolist()
            rec[stage + "_n"] = len(months)
            if len(months) >= 5:
                s = monthly(pd.Series(1, index=months).groupby(level=0).sum().to_dict(), cut)
                rec[stage], rec[stage + "_T50"] = t_month(s, Q), t_month(s, 0.5)
            y = pd.Series(months, dtype=str).str[:4].value_counts()
            yearly += [{"ingredient_id": ing, "stage": stage, "year": k, "value": int(v)} for k, v in y.items()]
        # 단계 순서: 시작 시점이 있는 단계만 빠른 순으로
        order = sorted([(rec[s], s) for s in STAGES if rec.get(s)])
        rec["순서"] = " → ".join(s for _, s in order)
        order50 = sorted([(rec[s + "_T50"], s) for s in STAGES if rec.get(s + "_T50")])
        rec["순서_T50"] = " → ".join(s for _, s in order50)
        rows.append(rec)

    on = pd.DataFrame(rows)
    on.insert(1, "name_ko", on["ingredient_id"].map(kw["name_ko"]))
    on.to_csv(PROCESSED / "procedure_path_onsets.csv", index=False, encoding="utf-8-sig")
    yr = pd.DataFrame(yearly).sort_values(["ingredient_id", "stage", "year"])
    yr.to_csv(PROCESSED / "procedure_path_yearly.csv", index=False, encoding="utf-8-sig")

    pd.set_option("display.width", 250)
    show = ["ingredient_id", "시술 검색", "시술 제품사 특허", "원료사 특허", "ODM 특허", "브랜드사 특허", "화장품 검색"]
    print(f"기간: {START} ~ {cut} (모든 단계 동일). T25 = 늘어난 양이 누적 25% 도달한 달, T50 = 50%")
    print("[T25]"); print(on[[c for c in show if c in on]].to_string(index=False))
    print("[T50]"); print(on[["ingredient_id"] + [c + "_T50" for c in show[1:] if c + "_T50" in on]].to_string(index=False))
    print("\n특허 건수:")
    print(on[["ingredient_id", "patent_coverage"] + [s + "_n" for s in STAGES[1:5]]].to_string(index=False))
    print("\n순서:")
    for r in on.itertuples():
        print(f"  {r.ingredient_id:12s} T25: {r.순서}")
        print(f"  {'':12s} T50: {r.순서_T50}")
    plot(yr, on)


def plot(yr, on):
    use_korean_font()
    NAMES = {"PDRN": "PDRN", "EXOSOME": "엑소좀", "NIACINAMIDE": "나이아신아마이드"}
    ids = ["PDRN", "EXOSOME", "NIACINAMIDE"]
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.8), sharey=True)
    for ax, ing in zip(axes, ids):
        d = yr[(yr["ingredient_id"] == ing) & (yr["year"].astype(int).between(2016, 2025))]
        for stage in STAGES:
            g = d[d["stage"] == stage].set_index("year")["value"]
            if g.empty or g.max() == 0:
                continue
            g = g.reindex([str(y) for y in range(2016, 2026)], fill_value=0)
            ax.plot(g.index.astype(int), g / g.max(), marker="o", ms=3, color=COLOR[stage],
                    lw=2.4 if "검색" in stage else 1.6, ls="-" if "검색" in stage else "--",
                    label=stage)
        ax.axvspan(2024.5, 2025.5, color="grey", alpha=0.12)
        ax.set_title(NAMES.get(ing, ing) + (" (비교군: 시술 없음)" if ing == "NIACINAMIDE" else ""))
        ax.grid(alpha=0.3)
    axes[0].legend(loc="upper left", fontsize=8)
    fig.suptitle("연도별 값 (단계별 최댓값 = 1). 실선 = 검색량, 점선 = 출원인 유형별 특허, "
                 "회색 = 특허가 덜 공개된 기간")
    fig.tight_layout()
    out = PROCESSED / "w4_procedure_path.png"
    fig.savefig(out, dpi=120)
    print(f"\n그래프 저장: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
