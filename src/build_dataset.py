"""세 가지 데이터를 하나의 표로 합치는 스크립트 (3주차).

왜 합치는가
  4주차 분석(언제 처음 늘었나, 몇 달 앞서나)은 같은 성분의 논문·특허·검색량을
  같은 달끼리 나란히 놓고 비교해야 한다. 그런데 지금은 파일도, 열 이름도, 기간도 제각각이다.
    - 네이버  : value_scaled 열, 2016-01 ~ (수집한 달 포함)
    - PubMed  : value 열,        2015-01 ~
    - KIPRIS  : value 열,        2010-01 ~ (전체 특허 / 화장품 특허 두 종류)
  그래서 모두 같은 모양(long format)으로 맞춘다.

결과 열
  ingredient_id, name_ko, group   : 성분 정보 (keywords.csv에서)
  stage    : science(논문) / patent(특허) / consumer(소비자 검색)
  source   : pubmed / kipris_cosmetic / kipris_all / naver / naver_procedure(시술 검색)
  month    : YYYY-MM
  value    : 값 (논문·특허는 건수, 네이버는 히알루론산=100 기준 상대값)
  value_type: count / index
  provisional: True면 아직 덜 채워진 값이라 분석할 때 조심해야 하는 달
      - 특허: 출원 후 약 18개월 뒤에 공개되므로 마지막 18개월은 실제보다 적다
  (네이버는 수집한 '이번 달'이 며칠치만 있어서 아예 뺀다)

실행
  python src/build_dataset.py
  -> data/processed/trend_long.csv          (분석에 쓰는 표)
     data/processed/check_merged_<날짜>.png  (학습용 성분 확인 그래프)
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from common import RAW_DIR, ROOT, load_keywords, today_tag

PROCESSED = ROOT / "data" / "processed"
PATENT_LAG_MONTHS = 18
STAGE_ORDER = ["procedure", "science", "patent", "consumer"]


def latest(prefix):
    files = sorted(RAW_DIR.glob(f"{prefix}_2*.csv"))
    if not files:
        raise SystemExit(f"data/raw/{prefix}_*.csv가 없어요. 수집 스크립트를 먼저 실행하세요.")
    print(f"읽는 파일: {files[-1].name}")
    return pd.read_csv(files[-1], encoding="utf-8-sig"), files[-1].stem.split("_")[-1]


def load_naver(prefix="naver"):
    df, tag = latest(prefix)
    # 수집한 달은 며칠치만 들어 있어서 다른 달과 비교할 수 없다 -> 제외
    collected = pd.Period(pd.Timestamp(tag), freq="M")
    df = df[pd.PeriodIndex(df["month"], freq="M") < collected]
    out = df[["ingredient_id", "stage", "source", "month"]].copy()
    out["value"] = df["value_scaled"]
    out["value_type"] = "index"
    return out[["ingredient_id", "stage", "source", "month", "value", "value_type"]]


def main():
    naver = load_naver()
    pubmed, _ = latest("pubmed")
    kipris, _ = latest("kipris")
    frames = [pubmed, kipris, naver]
    if list(RAW_DIR.glob("naver_procedure_2*.csv")):  # 시술 검색량 (선택)
        proc = load_naver("naver_procedure")
        proc["ingredient_id"] = proc["ingredient_id"].str.replace("_PROC", "", regex=False)
        frames.append(proc)
    long = pd.concat(frames, ignore_index=True)
    long["month"] = long["month"].astype(str)

    # 특허 마지막 18개월은 '잠정치'
    long["provisional"] = False
    pat = long["stage"] == "patent"
    last = pd.Period(long.loc[pat, "month"].max(), freq="M")
    cut = str(last - PATENT_LAG_MONTHS)
    long.loc[pat & (long["month"] > cut), "provisional"] = True

    kw = load_keywords()[["ingredient_id", "name_ko", "group"]]
    long = long.merge(kw, on="ingredient_id", how="left")
    long["stage"] = pd.Categorical(long["stage"], STAGE_ORDER, ordered=True)
    long = long.sort_values(["ingredient_id", "stage", "source", "month"])
    cols = ["ingredient_id", "name_ko", "group", "stage", "source", "month",
            "value", "value_type", "provisional"]
    long = long[cols].reset_index(drop=True)

    # 점검: 성분·출처 조합마다 달이 빠짐없이 이어지는지, 중복이 없는지
    dup = long.duplicated(["ingredient_id", "source", "month"]).sum()
    assert dup == 0, f"같은 성분·출처·달이 {dup}번 중복됐어요"
    for (i, s), g in long.groupby(["ingredient_id", "source"], observed=True):
        m = pd.PeriodIndex(g["month"], freq="M")
        assert len(m) == (m.max() - m.min()).n + 1, f"{i}/{s}에 빠진 달이 있어요"

    PROCESSED.mkdir(parents=True, exist_ok=True)
    out = PROCESSED / "trend_long.csv"
    long.to_csv(out, index=False, encoding="utf-8-sig")

    summary = long.groupby("source", observed=True).agg(
        성분수=("ingredient_id", "nunique"), 시작=("month", "min"), 끝=("month", "max"), 행수=("value", "size"))
    print(summary.to_string())
    print(f"\n특허 잠정치 구간: {cut} 이후 (출원 후 {PATENT_LAG_MONTHS}개월 공개 지연)")
    print(f"저장: {out.relative_to(ROOT)}  ({len(long):,}행)")
    plot(long)


def plot(long):
    """학습용 4개 성분: 연도별 값을 각 출처의 최댓값=1로 맞춰 한 그림에 겹쳐 그린다.
    단위가 다른 세 지표를 '언제 오르기 시작했나'만 비교하려는 확인용 그림이다."""
    ids = load_keywords(["train"])["ingredient_id"].tolist()
    d = long[(long.ingredient_id.isin(ids)) & (long.source.isin(["pubmed", "kipris_cosmetic", "naver"]))].copy()
    d["year"] = d["month"].str[:4].astype(int)
    d = d[(d.year >= 2012) & (d.year <= 2025)]
    y = d.groupby(["ingredient_id", "source", "year"], observed=True)["value"].sum().reset_index()
    y["norm"] = y["value"] / y.groupby(["ingredient_id", "source"])["value"].transform("max")
    style = {"pubmed": ("Papers (PubMed)", "#4C72B0", "-"),
             "kipris_cosmetic": ("Cosmetic patents (KIPRIS)", "#DD8452", "-"),
             "naver": ("Search (Naver)", "#55A868", "-")}
    fig, axes = plt.subplots(2, 2, figsize=(12, 7), sharex=True)
    for ax, i in zip(axes.flat, ids):
        for s, (label, color, ls) in style.items():
            g = y[(y.ingredient_id == i) & (y.source == s)]
            ax.plot(g.year, g.norm, ls, color=color, marker="o", ms=3, label=label)
        ax.axvspan(2024.5, 2025.5, color="grey", alpha=0.15)
        ax.set_title(i)
        ax.grid(alpha=0.3)
    axes[0, 0].legend(loc="upper left", fontsize=8)
    fig.suptitle("Yearly totals scaled to each source's max (grey = patents still incomplete)")
    fig.tight_layout()
    out = PROCESSED / f"check_merged_{today_tag()}.png"
    fig.savefig(out, dpi=120)
    print(f"그래프 저장: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
