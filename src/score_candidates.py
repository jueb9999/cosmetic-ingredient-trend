"""5주차: 후보 성분 점수화 + 백테스트.

H2 가설: "논문·특허는 이미 오르는데 소비자 검색은 아직 낮은 성분"이 다음에 뜬다.

점수 (기준 시점 T에서 그때 볼 수 있던 데이터만 사용)
  - 논문 모멘텀  : 최근 12개월 논문 수 vs 그 전 12개월 (로그 증가율)
  - 특허 모멘텀  : 같은 계산. 단 특허는 출원 후 18개월 뒤 공개되므로 T-18개월까지만 사용
  - 검색 여지    : 최근 12개월 검색 수준이 낮을수록 높음 (-log 수준)
  - (별도) 시술 신호: 시술 검색량 증가율. 시술 검색어가 있는 성분만 있어서 점수에는 넣지 않고 따로 표시
  각 항목을 성분 사이 백분위(0~1)로 바꾼 뒤 가중합:
    H2 점수 = 0.6 x 위쪽 신호(논문·특허 평균) + 0.4 x 검색 여지

백테스트: 과거 시점 T마다 점수를 매기고, 그 뒤 3년 동안 검색량이 얼마나 늘었는지와
순위 상관(스피어만)을 본다. 비교 기준으로 "이미 오르는 검색량이 계속 오른다"(단순 추세)도 같이 본다.
"""
import argparse

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from common import ROOT, load_keywords

PROCESSED = ROOT / "data" / "processed"
PATENT_LAG = 18      # 특허 공개 지연 (개월)
HORIZON = 36         # 백테스트: 몇 개월 뒤 검색량을 결과로 볼지
K_COUNT = 5          # 건수 증가율 계산 시 더하는 값 (0 -> 2건 같은 작은 변화가 튀지 않게)
K_INDEX = 0.5        # 검색 지수에 더하는 값
W_UP, W_ROOM = 0.6, 0.4
DOUBLED = np.log(2)
RHO_SIG = 0.44       # 성분 20개일 때 p<0.05가 되려면 필요한 |순위상관|  # 백테스트 '적중' = 3년 뒤 검색량이 2배 이상

# 그래프 색: 기본 검증 팔레트 1~4번 (순서 고정)
C = {"pub": "#2a78d6", "pat": "#eb6834", "room": "#1baf7a", "proc": "#eda100"}
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"


# ---------- 데이터 ----------
def load_series():
    d = pd.read_csv(PROCESSED / "trend_long.csv", encoding="utf-8-sig")
    d = d[d.source.isin(["pubmed", "kipris_cosmetic", "naver", "naver_procedure"])]
    out = {}
    for (ing, src), g in d.groupby(["ingredient_id", "source"]):
        out[(ing, src)] = pd.Series(g.value.values, index=pd.PeriodIndex(g.month, freq="M")).sort_index()
    return out


def window(s, end, n=12):
    """end를 포함한 최근 n개월. 데이터가 모자라면 None."""
    w = s[(s.index > end - n) & (s.index <= end)]
    return w if len(w) == n else None


def growth(s, end, k, how="sum"):
    a, b = window(s, end), window(s, end - 12)
    if a is None or b is None:
        return np.nan
    f = (lambda w: w.sum()) if how == "sum" else (lambda w: w.mean())
    return float(np.log((f(a) + k) / (f(b) + k)))


def features(series, ings, asof):
    rows = []
    for ing in ings:
        pub = series.get((ing, "pubmed"))
        pat = series.get((ing, "kipris_cosmetic"))
        nav = series.get((ing, "naver"))
        proc = series.get((ing, "naver_procedure"))
        lvl = window(nav, asof)
        r = {
            "ingredient_id": ing,
            "pub_mom": growth(pub, asof, K_COUNT),
            "pat_mom": growth(pat, asof - PATENT_LAG, K_COUNT),
            "search_level": np.nan if lvl is None else float(lvl.mean()),
            "search_mom": growth(nav, asof, K_INDEX, "mean"),
            "proc_mom": np.nan if proc is None else growth(proc, asof, K_INDEX, "mean"),
            "proc_level": np.nan if proc is None or window(proc, asof) is None else float(window(proc, asof).mean()),
        }
        pw, tw = window(pub, asof), window(pat, asof - PATENT_LAG)
        r["papers_12m"] = np.nan if pw is None else float(pw.sum())
        r["patents_12m"] = np.nan if tw is None else float(tw.sum())
        r["room"] = -np.log(r["search_level"] + K_INDEX)
        rows.append(r)
    f = pd.DataFrame(rows)
    pct = lambda c: f[c].rank(pct=True)
    f["pub_pct"], f["pat_pct"], f["room_pct"] = pct("pub_mom"), pct("pat_mom"), pct("room")
    f["up_pct"] = f[["pub_pct", "pat_pct"]].mean(axis=1)
    return f


def add_scores(f, w_up=W_UP, w_pat=0.5):
    up = w_pat * f.pat_pct + (1 - w_pat) * f.pub_pct
    return w_up * up + (1 - w_up) * f.room_pct


def outcome(series, ings, asof):
    out = {}
    for ing in ings:
        nav = series[(ing, "naver")]
        now, fut = window(nav, asof), window(nav, asof + HORIZON)
        out[ing] = np.nan if now is None or fut is None else float(np.log((fut.mean() + K_INDEX) / (now.mean() + K_INDEX)))
    return pd.Series(out)


def label(r):
    if r.papers_12m + r.patents_12m < 10:
        return "근거 부족 (논문+특허 연 10건 미만)"
    if r.room_pct < 0.35:
        return "이미 대중화"
    if r.up_pct >= 0.6 and r.room_pct >= 0.5:
        return "선행 신호"
    return "관찰"


# ---------- 백테스트 ----------
def backtest(series, ings, last):
    cutoffs = pd.period_range(pd.Period("2017-12", "M"), last - HORIZON, freq="M")[::6]
    rows, ranks = [], []
    for t in cutoffs:
        f = features(series, ings, t).set_index("ingredient_id")
        y = outcome(series, ings, t)
        variants = {
            "H2 점수": add_scores(f.reset_index()).values,
            "위쪽 신호만": f.up_pct.values,
            "단순 추세(검색 증가율)": f.search_mom.values,
            "항목: 논문 모멘텀": f.pub_mom.values,
            "항목: 특허 모멘텀": f.pat_mom.values,
            "항목: 검색 여지": f.room.values,
        }
        for name, sc in variants.items():
            s = pd.Series(sc, index=f.index)
            ok = s.notna() & y.notna()
            rho = spearmanr(s[ok], y[ok]).statistic
            top = s[ok].nlargest(5).index
            rows.append({"asof": str(t), "variant": name, "spearman": rho,
                         "top5_hit": float((y[top] >= DOUBLED).mean()),
                         "base_hit": float((y[ok] >= DOUBLED).mean()),
                         "top5": ",".join(top)})
        h2 = pd.Series(add_scores(f.reset_index()).values, index=f.index)
        for ing in ["PDRN", "NIACINAMIDE", "RETINOL", "CICA"]:
            ranks.append({"asof": str(t), "ingredient_id": ing,
                          "h2_rank": int(h2.rank(ascending=False)[ing]), "n": len(h2)})
    return pd.DataFrame(rows), pd.DataFrame(ranks)


# ---------- 그래프 ----------
def style(ax):
    ax.grid(axis="x", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    for s in ["top", "right", "left"]:
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(INK2)
    ax.tick_params(colors=INK2, labelsize=8)


def plot(cur, bt, path):
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(13, 6.5), gridspec_kw={"width_ratios": [1.3, 1]})
    fig.patch.set_facecolor("#fcfcfb")
    c = cur.sort_values("score")
    y = np.arange(len(c))
    parts = [("pub_pct", W_UP * 0.5, "Paper momentum", C["pub"]),
             ("pat_pct", W_UP * 0.5, "Patent momentum", C["pat"]),
             ("room_pct", 1 - W_UP, "Search headroom", C["room"])]
    left = np.zeros(len(c))
    for col, w, lab, col_c in parts:
        v = (c[col] * w).values
        a1.barh(y, v, left=left, height=0.62, color=col_c, label=lab, edgecolor="#fcfcfb", linewidth=1.5)
        left += v
    names = [f"{i}{' *' if g == 'train' else ''}" for i, g in zip(c.ingredient_id, c.group)]
    a1.set_yticks(y, names)
    for yi, (sc, pm) in enumerate(zip(c.score, c.proc_mom)):
        txt = f"{sc:.2f}" + ("" if np.isnan(pm) else f"   procedure {np.exp(pm) - 1:+.0%}")
        a1.text(sc + 0.01, yi, txt, va="center", fontsize=7.5, color=INK2)
    a1.set_xlim(0, 1.25)
    a1.set_title(f"H2 score as of {cur["asof"].iloc[0]}  (* = training ingredient)", fontsize=10, color=INK, loc="left")
    a1.legend(loc="lower right", fontsize=8, frameon=False)
    style(a1)

    styles = {"H2 점수": (C["pat"], "H2 score"), "위쪽 신호만": (C["pub"], "Upstream only"),
              "단순 추세(검색 증가율)": (INK2, "Naive: search trend")}
    for name, (col, lab) in styles.items():
        b = bt[bt.variant == name]
        x = pd.PeriodIndex(b["asof"], freq="M").to_timestamp()
        a2.plot(x, b.spearman, color=col, lw=2, marker="o", ms=5, label=lab)
    a2.axhspan(-RHO_SIG, RHO_SIG, color=GRID, alpha=0.6, lw=0)
    a2.text(x.min(), RHO_SIG + 0.02, "not significant (|rho| < 0.44, n=20, p>0.05)", fontsize=7.5, color=INK2)
    a2.axhline(0, color=INK2, lw=0.8)
    a2.set_ylim(-1, 1)
    a2.set_title(f"Backtest: rank corr. with search growth over next {HORIZON} months", fontsize=10, color=INK, loc="left")
    a2.set_ylabel("Spearman", fontsize=8, color=INK2)
    a2.legend(fontsize=8, frameon=False, loc="lower left")
    style(a2)
    a2.grid(axis="y", color=GRID, lw=0.8)
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor=fig.get_facecolor())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--asof", help="기준 달 (기본: 데이터 마지막 달)")
    a = ap.parse_args()

    kw = load_keywords(["train", "candidate"])
    ings = kw.ingredient_id.tolist()
    series = load_series()
    last = max(s.index.max() for (i, src), s in series.items() if src == "naver")
    asof = pd.Period(a.asof, freq="M") if a.asof else last

    # 1) 현재 점수
    cur = features(series, ings, asof)
    cur["score"] = add_scores(cur)
    cur["status"] = cur.apply(label, axis=1)
    cur = cur.merge(kw[["ingredient_id", "name_ko", "group"]], on="ingredient_id")
    cur["asof"] = str(asof)
    cur["patent_until"] = str(asof - PATENT_LAG)
    cur["rank"] = cur.score.rank(ascending=False).astype(int)

    # 2) 가중치 민감도: 가중치를 바꿔도 상위 5개가 비슷한가
    base_top = set(cur.nlargest(5, "score").ingredient_id)
    sens = []
    for w_up in [0.5, 0.6, 0.7]:
        for w_pat in [0.3, 0.5, 0.7]:
            s = add_scores(cur, w_up, w_pat)
            top = set(cur.ingredient_id[s.nlargest(5).index])
            sens.append({"w_upstream": w_up, "w_patent_in_upstream": w_pat,
                         "spearman_vs_base": spearmanr(s, cur.score).statistic,
                         "top5_overlap": len(top & base_top), "top5": ",".join(sorted(top))})
    sens = pd.DataFrame(sens)
    cur["top5_in_all_weights"] = cur.ingredient_id.map(
        lambda i: sum(i in t.split(",") for t in sens.top5))

    # 3) 백테스트
    bt, ranks = backtest(series, ings, last)

    cols = ["rank", "ingredient_id", "name_ko", "group", "score", "status", "pub_pct", "pat_pct", "room_pct",
            "pub_mom", "pat_mom", "papers_12m", "patents_12m", "search_level", "search_mom",
            "proc_mom", "proc_level", "top5_in_all_weights", "asof", "patent_until"]
    cur = cur.sort_values("score", ascending=False)
    cur[cols].round(3).to_csv(PROCESSED / "scores.csv", index=False, encoding="utf-8-sig")
    sens.round(3).to_csv(PROCESSED / "score_sensitivity.csv", index=False, encoding="utf-8-sig")
    bt.round(3).to_csv(PROCESSED / "score_backtest.csv", index=False, encoding="utf-8-sig")
    ranks.to_csv(PROCESSED / "score_backtest_train_ranks.csv", index=False, encoding="utf-8-sig")
    plot(cur, bt, PROCESSED / "w5_scores.png")

    pd.set_option("display.width", 200)
    print(f"기준 {asof} (특허는 {asof - PATENT_LAG}까지)\n")
    print(cur[["rank", "ingredient_id", "group", "score", "status", "pub_mom", "pat_mom",
               "papers_12m", "patents_12m", "search_level", "proc_mom", "top5_in_all_weights"]].round(2).to_string(index=False))
    print("\n가중치 민감도:\n", sens.round(2).to_string(index=False))
    print("\n백테스트 요약 (시점 평균):")
    print(bt.groupby("variant")[["spearman", "top5_hit", "base_hit"]].agg(["mean", "min", "max"]).round(2).to_string())
    print("\n학습 성분 순위 (H2 점수, 20개 중):")
    print(ranks.pivot(index="asof", columns="ingredient_id", values="h2_rank").to_string())
    print("\n저장: scores.csv, score_sensitivity.csv, score_backtest.csv, w5_scores.png")


if __name__ == "__main__":
    main()
