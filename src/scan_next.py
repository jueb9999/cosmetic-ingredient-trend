"""7주차 전: "PDRN 다음" 후보 탐색.

5주차 점수는 1주차에 고른 20개 성분 안에서만 순위를 매겨서, 업계에서 거론되는 새 성분
(NAD, 아젤라산, PDLLA 등)을 볼 수 없었다. 그래서 새 후보의 검색량을 따로 모아
"지금 모습이 PDRN이 뜨기 직전과 닮았는가"를 본다.

비교 기준: PDRN 화장품 검색은 2021~2022년에 낮은 수준에서 꾸준히 오르다가 2023년에 폭발했다.
  (2022-10 기준 12개월 평균 13.8, 전년 대비 +44%)

지표 (모두 네이버 검색, 히알루론산 평균 = 100 기준)
  level      최근 12개월 평균
  growth     최근 12개월 / 그 전 12개월 - 1
  steady     최근 12개월 중 전년 같은 달보다 높은 달의 비율 (꾸준히 오르면 1에 가까움)
  from_peak  최근 3개월 평균 / 지금까지 가장 높았던 3개월 평균 (1 = 지금이 정점)
판정
  PDRN 직전과 닮음 : growth >= 30%, steady >= 0.75, from_peak >= 0.8, level 1~50
  급등 후 조정     : growth >= 30% 이지만 from_peak < 0.8 (한 번 튄 뒤 내려오는 중)
  아직 작음        : growth >= 30% 이지만 level < 1
  유행 지남        : from_peak < 0.7
  정체             : 나머지
"""
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from common import ROOT, use_korean_font

PROCESSED = ROOT / "data" / "processed"
RAW = ROOT / "data" / "raw"
END = pd.Period("2026-10", "M")
K = 0.5
PROC_PAIR = {"PDRN": "PDRN", "NAD": "NAD_PROC", "PDLLA": "PDLLA_PROC", "ECM": "ECM_PROC"}
PROC_NAME = {"PDRN": "리쥬란 (PDRN)", "PDLLA_PROC": "쥬베룩 (PDLLA)", "ECM_PROC": "리투오 (ECM)",
             "NAD_PROC": "NAD 주사"}

INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]   # 기본 검증 팔레트 1~4번
GRAY = "#8a8984"
SHORT = {"COPPER_PEPTIDE": "구리 펩타이드", "PDLLA": "PDLLA", "ECM": "ECM", "NAD": "NAD·NMN", "RICE": "쌀"}
LABEL_OFFSET = {"COPPER_PEPTIDE": (-70, 8), "RICE": (6, 4), "PDLLA": (-36, -13), "ECM": (6, -11), "SPICULE": (6, -12), "NAD": (-10, -14)}


def latest(prefix):
    return sorted(RAW.glob(f"{prefix}_2*.csv"))[-1]


def to_series(df, col):
    return {i: pd.Series(g[col].values, index=pd.PeriodIndex(g.month, freq="M")).sort_index()
            for i, g in df.groupby("ingredient_id")}


def load():
    t = pd.read_csv(PROCESSED / "trend_long.csv", encoding="utf-8-sig")
    cos = to_series(t[t.source == "naver"], "value")
    scan = pd.read_csv(latest("naver_scan"), encoding="utf-8-sig")
    meta = pd.read_csv(ROOT / "config" / "scan_keywords.csv", encoding="utf-8-sig")
    stage = dict(zip(meta.ingredient_id, meta.stage))
    for i, s in to_series(scan, "value_scaled").items():
        if stage.get(i) == "consumer":
            cos[i] = s
    proc = to_series(pd.read_csv(latest("naver_procedure"), encoding="utf-8-sig"), "value_scaled")
    proc.update({i: s for i, s in to_series(scan, "value_scaled").items() if stage.get(i) == "procedure"})
    return cos, proc, meta


def mean(s, end, n=12):
    return float(s[(s.index > end - n) & (s.index <= end)].mean())


def metrics(s, end=END):
    lv, prev = mean(s, end), mean(s, end - 12)
    last12 = s[(s.index > end - 12) & (s.index <= end)]
    yago = s.reindex(last12.index - 12)
    r3 = s.rolling(3).mean()
    return {"level": lv, "growth": (lv + K) / (prev + K) - 1,
            "steady": float((last12.values > yago.values).mean()),
            "from_peak": float(r3.iloc[-1] / r3.max()) if r3.max() > 0 else np.nan,
            "peak_month": str(r3.idxmax())}


def judge(r):
    if r.growth >= 0.3:
        if r.from_peak < 0.8:
            return "급등 후 조정"
        if r.level < 1:
            return "아직 작음"
        if r.steady >= 0.75 and r.level <= 50:
            return "PDRN 직전과 닮음"
    if r.from_peak < 0.7:
        return "유행 지남"
    return "정체"


def main():
    cos, proc, meta = load()
    names = dict(zip(meta.ingredient_id, meta.name_ko))
    kw = pd.read_csv(ROOT / "config" / "keywords.csv", encoding="utf-8-sig")
    names.update(dict(zip(kw.ingredient_id, kw.name_ko)))
    new = set(meta.ingredient_id)

    rows = []
    for i, s in cos.items():
        r = {"ingredient_id": i, "name_ko": names.get(i, i), "new_candidate": i in new, **metrics(s)}
        p = PROC_PAIR.get(i)
        if p in proc:
            pm = metrics(proc[p])
            r.update({"procedure": PROC_NAME.get(p, p), "proc_level": pm["level"],
                      "proc_growth": pm["growth"], "proc_peak_month": pm["peak_month"]})
        rows.append(r)
    d = pd.DataFrame(rows)
    d["judgement"] = d.apply(judge, axis=1)
    order = ["PDRN 직전과 닮음", "급등 후 조정", "아직 작음", "정체", "유행 지남"]
    d["o"] = d.judgement.map(order.index)
    d = d.sort_values(["o", "growth"], ascending=[True, False]).drop(columns="o")

    # PDRN이 뜨기 전 궤적 (매년 10월 기준)
    path = pd.DataFrame([{"year": y, **metrics(cos["PDRN"], pd.Period(f"{y}-10", "M"))} for y in range(2018, 2027)])

    d.round(3).to_csv(PROCESSED / "next_candidates.csv", index=False, encoding="utf-8-sig")
    path.round(3).to_csv(PROCESSED / "pdrn_path.csv", index=False, encoding="utf-8-sig")
    plot(d, path, proc)

    pd.set_option("display.width", 200)
    print(d[["ingredient_id", "name_ko", "judgement", "level", "growth", "steady", "from_peak", "peak_month",
             "procedure", "proc_level", "proc_growth", "proc_peak_month"]].round(2).to_string(index=False))
    print("\nPDRN 궤적 (매년 10월):\n", path[["year", "level", "growth", "steady"]].round(2).to_string(index=False))
    print("\n저장: next_candidates.csv, pdrn_path.csv, w7_next_candidates.png")


def style(ax):
    for s in ["top", "right"]:
        ax.spines[s].set_visible(False)
    for s in ["left", "bottom"]:
        ax.spines[s].set_color(INK2)
    ax.tick_params(colors=INK2, labelsize=8)
    ax.grid(color=GRID, lw=0.8)
    ax.set_axisbelow(True)


def plot(d, path, proc):
    use_korean_font()
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(14, 6.2))
    fig.patch.set_facecolor("#fcfcfb")

    # 왼쪽: 지금 위치 (수준 x 증가율) + PDRN이 지나온 길
    x = lambda v: np.maximum(v, 0.05)
    y = lambda v: np.clip(v * 100, -60, 300)
    a1.plot(x(path.level), y(path.growth), color=GRAY, lw=1.5, zorder=2)
    a1.scatter(x(path.level), y(path.growth), color=GRAY, s=30, zorder=3)
    for _, r in path.iterrows():
        a1.annotate(f"PDRN {r.year}년", (x(r.level), y(r.growth)), xytext=(5, -10), textcoords="offset points",
                    fontsize=7.5, color=INK2)
    for _, r in d[d.ingredient_id != "PDRN"].iterrows():
        hot = r.judgement in ("PDRN 직전과 닮음", "급등 후 조정", "아직 작음")
        a1.scatter(x(r.level), y(r.growth), s=55, zorder=4, edgecolor="#fcfcfb", linewidth=1.5,
                   color=SERIES[0] if r.new_candidate else SERIES[1], alpha=1 if hot else 0.35)
        if hot or r.ingredient_id in ("SPICULE", "EXOSOME"):
            txt = SHORT.get(r.ingredient_id, r.name_ko) + (f" (+{r.growth:.0%}, 축 밖)" if r.growth * 100 > 300 else "")
            a1.annotate(txt, (x(r.level), y(r.growth)), xytext=LABEL_OFFSET.get(r.ingredient_id, (6, 4)),
                        textcoords="offset points", fontsize=8, color=INK)
    a1.scatter([], [], color=SERIES[0], label="7주차 새 후보")
    a1.scatter([], [], color=SERIES[1], label="1주차 20개 성분")
    a1.plot([], [], color=GRAY, marker="o", label="PDRN이 지나온 길 (매년 10월)")
    a1.set_xscale("log")
    a1.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:g}"))
    a1.axhline(30, color=INK2, lw=0.8, ls="--")
    a1.text(0.06, 33, "연 +30%", fontsize=7.5, color=INK2)
    a1.set_xlabel("최근 12개월 검색 수준 (히알루론산 = 100, 로그 눈금)", fontsize=8.5, color=INK2)
    a1.set_ylabel("1년 전보다 늘어난 비율 (%)", fontsize=8.5, color=INK2)
    a1.set_title("지금 각 성분의 위치와 PDRN이 지나온 길", fontsize=10, color=INK, loc="left")
    a1.set_ylim(-60, 330)
    a1.legend(fontsize=8, frameon=False, loc="upper left")
    style(a1)

    # 오른쪽: 시술 검색량 (3개월 이동평균)
    for c, key in zip(SERIES, ["PDRN", "PDLLA_PROC", "ECM_PROC", "NAD_PROC"]):
        s = proc[key].rolling(3).mean()
        s = s[s.index >= pd.Period("2018-01", "M")]
        a2.plot(s.index.to_timestamp(), s.values, color=c, lw=2, label=PROC_NAME[key])
        a2.annotate(PROC_NAME[key], (s.index[-1].to_timestamp(), s.iloc[-1]), xytext=(4, -8 if key == "PDLLA_PROC" else 4),
                    textcoords="offset points", fontsize=8, color=INK, va="center")
    a2.set_title("스킨부스터 시술 검색량 (3개월 평균)", fontsize=10, color=INK, loc="left")
    a2.set_ylabel("검색 지수 (히알루론산 = 100)", fontsize=8.5, color=INK2)
    a2.legend(fontsize=8, frameon=False, loc="upper left")
    a2.set_xlim(right=pd.Timestamp("2028-03-01"))
    style(a2)
    fig.tight_layout()
    fig.savefig(PROCESSED / "w7_next_candidates.png", dpi=150, facecolor=fig.get_facecolor())


# ---------- 8주차: 새 후보 3개의 논문·특허 ----------
UPSTREAM = {"PDRN": "PDRN (비교)", "AZELAIC": "아젤라산", "NAD": "NAD·NMN", "ECM": "ECM"}
ECM_TITLE = "세포외기질|세포외 기질|ECM"
ECM_TEXT = "탈세포|무세포"


def upstream():
    """새 후보의 연도별 논문 수·화장품 특허 수를 PDRN과 나란히 놓는다.

    ECM은 '이 추출물이 세포외기질을 늘린다'처럼 효과 설명으로만 쓰인 특허가 많아서
    제목에 세포외기질·ECM이 있거나 탈세포·무세포 가공을 다루는 특허만 센다.
    """
    t = pd.read_csv(PROCESSED / "trend_long.csv", encoding="utf-8-sig")
    pub = pd.concat([t[(t.source == "pubmed") & (t.ingredient_id == "PDRN")][["ingredient_id", "month", "value"]],
                     pd.read_csv(latest("pubmed_scan"), encoding="utf-8-sig")[["ingredient_id", "month", "value"]]])
    items = pd.read_csv(sorted(RAW.glob("kipris_scan_items_2*.csv"))[-1], encoding="utf-8-sig")
    items = items[items.is_cosmetic_ipc]
    text = items.inventionTitle.fillna("") + " " + items.astrtCont.fillna("")
    ecm_ok = items.inventionTitle.fillna("").str.contains(ECM_TITLE) | text.str.contains(ECM_TEXT)
    items = items[(items.ingredient_id != "ECM") | ecm_ok]
    items = items.assign(month=items.applicationDate.astype(str).str[:4] + "-" + items.applicationDate.astype(str).str[4:6])
    pat = pd.concat([items.groupby(["ingredient_id", "month"]).size().rename("value").reset_index(),
                     t[(t.source == "kipris_cosmetic") & (t.ingredient_id == "PDRN")][["ingredient_id", "month", "value"]]])

    rows, yearly = [], []
    for kind, df, end in [("논문", pub, END), ("화장품 특허", pat, END - 18)]:
        for ing in UPSTREAM:
            g = df[df.ingredient_id == ing]
            s = (g.groupby("month").value.sum().reindex(pd.period_range("2010-01", END, freq="M").astype(str), fill_value=0))
            s.index = pd.PeriodIndex(s.index, freq="M")
            last, prev = mean(s, end) * 12, mean(s, end - 12) * 12
            rows.append({"ingredient_id": ing, "name": UPSTREAM[ing], "kind": kind, "until": str(end),
                         "last_12m": last, "prev_12m": prev, "growth": (last + 5) / (prev + 5) - 1})
            for y, v in s.groupby(s.index.year).sum().items():
                yearly.append({"ingredient_id": ing, "name": UPSTREAM[ing], "kind": kind, "year": y, "value": v,
                               "complete": (y < END.year) if kind == "논문" else (y <= (END - 18).year - 1)})
    summ, yearly = pd.DataFrame(rows), pd.DataFrame(yearly)
    summ.round(3).to_csv(PROCESSED / "next_candidates_upstream.csv", index=False, encoding="utf-8-sig")
    yearly.to_csv(PROCESSED / "next_candidates_upstream_yearly.csv", index=False, encoding="utf-8-sig")
    plot_upstream(yearly)
    print("\n새 후보 논문·특허 (최근 12개월, 특허는 18개월 공개 지연만큼 앞까지):")
    print(summ.pivot(index="name", columns="kind", values=["last_12m", "growth"]).round(2).to_string())
    return summ


def plot_upstream(yearly):
    use_korean_font()
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.6))
    fig.patch.set_facecolor("#fcfcfb")
    for ax, kind in zip(axes, ["논문", "화장품 특허"]):
        for c, ing in zip([GRAY] + SERIES[:3], UPSTREAM):
            g = yearly[(yearly.kind == kind) & (yearly.ingredient_id == ing) & yearly.year.between(2015, 2026)]
            done, part = g[g.complete], g[~g.complete | (g.year == g[g.complete].year.max())]
            ax.plot(done.year, done.value, color=c, lw=2.2, marker="o", ms=4, label=UPSTREAM[ing])
            ax.plot(part.year, part.value, color=c, lw=1.5, ls=":", marker="o", ms=3, mfc="none")
        ax.set_title(f"{kind} 수 (연간)", fontsize=10, color=INK, loc="left")
        style(ax)
    axes[0].legend(fontsize=8.5, frameon=False, loc="upper left")
    fig.text(0.01, 0.01, "점선 = 아직 덜 모인 해 (논문: 2026년은 10월까지, 특허: 출원 후 18개월 뒤 공개되어 2024년 하반기부터 덜 공개됨)",
             fontsize=8, color=INK2)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(PROCESSED / "w8_new_candidates_upstream.png", dpi=150, facecolor=fig.get_facecolor())


if __name__ == "__main__":
    main()
    upstream()
