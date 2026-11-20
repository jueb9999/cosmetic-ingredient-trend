"""어떤 지표가 몇 달 먼저 움직이는지 계산하는 스크립트 (4주차).

질문(H1): 논문(science)·특허(patent)가 소비자 검색(consumer)보다 일정한 시차로 먼저 오르는가?
학습용 4개 성분(PDRN, CICA, NIACINAMIDE, RETINOL)으로 시차를 배우고,
같은 계산을 후보 성분에도 해 두어 5주차 점수화에 쓴다.

준비 (모든 방법 공통)
  - 월별 값은 들쭉날쭉하고 계절성(1월 튐 등)이 있어서 '최근 12개월 합계(R)'로 부드럽게 만든다.
    네이버는 상대지수라 12개월 평균을 쓴다(모양은 합계와 같다).
  - 특허는 마지막 18개월(provisional)이 덜 채워져 있어 분석에서 뺀다.

방법 1. 시작점(onset) - 전년 대비 규칙
  R이 1년 전보다 30% 이상 크고(성장 중), R이 최댓값의 10% 이상인(너무 작은 값의 흔들림 제외) 달을
  '오르는 달'로 본다. 오르는 달이 6개월 이상 이어진 구간(중간 2개월 이하 쉬는 것은 허용) 중
  R이 가장 많이 늘어난 구간을 '본격 상승'으로 보고, 그 첫 달을 시작점으로 한다.
  * 12개월 합계·전년 대비를 쓰기 때문에 실제 시작보다 몇 달 늦게 잡힌다. 하지만 모든 지표에
    똑같이 적용되므로 '지표 사이의 시차'에는 영향이 거의 없다.

방법 2. 시작점(onset) - 변화점 탐지
  log(R) 그래프를 직선 1~4개로 나눠 가장 잘 맞는 방법을 찾는다(BIC로 직선 개수 결정,
  한 직선은 최소 12개월). 연 30% 이상 오르는 직선 구간 중 R이 가장 많이 늘어난 구간의 첫 달을 시작점으로 한다.
  (ruptures 패키지와 같은 원리. Python 3.14용 ruptures가 없어 numpy로 직접 구현)

방법 3. 교차상관(CCF)
  두 지표의 '전년 대비 성장률'을 만들고, 앞선 지표를 k개월 뒤로 밀었을 때 상관이 가장 큰 k를 찾는다.
  k > 0 이면 앞선 지표(논문·특허)가 k개월 먼저, k < 0 이면 오히려 검색이 먼저.

방법 4. 그랜저 인과 검정
  '앞선 지표의 과거 값을 알면 검색량의 미래를 더 잘 맞히는가'를 검정한다(1~12개월 시차).
  월별 값에 log를 씌우고 12개월 전 값과의 차이를 써서 계절성·추세를 없앤 뒤 검정한다.
  12개 시차 중 가장 작은 p값을 쓰므로 여러 번 시험한 효과를 보정(×12, 본페로니)한 값도 함께 낸다.

주의
  - 네이버 데이터는 2016-01부터라 R은 2016-12, 전년 대비는 2017-12부터 계산된다.
    검색 시작점이 이 첫 달에 잡히면 실제로는 더 일찍 시작했을 수 있다(censored=True).
  - 상관·그랜저는 '먼저 움직인다'는 통계적 관계일 뿐 원인이라는 뜻은 아니다.

실행
  python src/analyze_lead_lag.py
  -> data/processed/onsets.csv, data/processed/lead_lag.csv, data/processed/w4_onsets_train.png
"""
import contextlib
import io
import warnings

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import adfuller, grangercausalitytests

from common import ROOT, load_keywords

PROCESSED = ROOT / "data" / "processed"
SOURCES = ["pubmed", "kipris_cosmetic", "naver"]
PAIRS = [("pubmed", "naver"), ("kipris_cosmetic", "naver"), ("pubmed", "kipris_cosmetic")]
LABEL = {"pubmed": "Papers", "kipris_cosmetic": "Cosmetic patents", "naver": "Search"}
COLOR = {"pubmed": "#4C72B0", "kipris_cosmetic": "#DD8452", "naver": "#55A868"}

GROWTH = 0.30        # 전년 대비 30% 이상 = 오르는 중
MIN_SHARE = 0.10     # 최댓값의 10% 미만은 흔들림으로 보고 무시
MIN_RUN = 6          # 6개월 이상 이어져야 본격 상승
MAX_GAP = 2          # 중간에 2개월까지는 쉬어도 같은 구간
MIN_SEG = 12         # 변화점 탐지: 한 직선은 최소 12개월
MAX_SEGS = 4
CCF_RANGE = range(-24, 37)
GRANGER_MAXLAG = 12


# ---------- 데이터 준비 ----------
def load_series():
    d = pd.read_csv(PROCESSED / "trend_long.csv", encoding="utf-8-sig")
    d = d[d.source.isin(SOURCES) & ~d.provisional]
    out = {}
    for (ing, src), g in d.groupby(["ingredient_id", "source"]):
        s = pd.Series(g.value.values, index=pd.PeriodIndex(g.month, freq="M")).sort_index()
        out[(ing, src)] = s
    return out


def smooth(s, src):
    r = s.rolling(12).mean() if src == "naver" else s.rolling(12).sum()
    return r.dropna()


def is_low_volume(r, src):
    # 논문·특허: 연 12건 미만(월 1건 미만), 네이버: 12개월 평균 지수 1 미만(앵커 100 대비)
    return bool(r.max() < (1.0 if src == "naver" else 12))


# ---------- 방법 1: 전년 대비 규칙 ----------
def onset_yoy(r):
    if r.max() <= 0:
        return None
    rising = (r / r.shift(12) - 1 >= GROWTH) & (r >= MIN_SHARE * r.max())
    months = list(r.index[rising.fillna(False).values])
    runs, cur = [], []
    for m in months:
        if cur and (m - cur[-1]).n > MAX_GAP + 1:
            runs.append(cur)
            cur = []
        cur.append(m)
    if cur:
        runs.append(cur)
    runs = [x for x in runs if (x[-1] - x[0]).n + 1 >= MIN_RUN]
    if not runs:
        return None

    def gain(run):
        before = r.get(run[0] - 1, r.loc[run[0]])
        return r.loc[run[-1]] - before

    return max(runs, key=gain)[0]


# ---------- 방법 2: 변화점(직선 나누기) ----------
def _seg_cost_table(y):
    """모든 구간 [i, j)에 직선을 맞췄을 때의 오차제곱합을 누적합으로 빠르게 계산."""
    n = len(y)
    x = np.arange(n, dtype=float)

    def S(a):
        return np.concatenate([[0.0], np.cumsum(a)])

    s1, sx, sy, sxx, sxy, syy = S(np.ones(n)), S(x), S(y), S(x * x), S(x * y), S(y * y)

    def cost(i, j):
        k = s1[j] - s1[i]
        X, Y = sx[j] - sx[i], sy[j] - sy[i]
        XX, XY, YY = sxx[j] - sxx[i], sxy[j] - sxy[i], syy[j] - syy[i]
        var_x = XX - X * X / k
        cov = XY - X * Y / k
        slope = cov / var_x if var_x > 0 else 0.0
        sse = (YY - Y * Y / k) - slope * cov
        return max(sse, 0.0), slope

    return cost


def segment(y):
    """y를 직선 1~MAX_SEGS개로 나눈 최적 구간 목록 [(시작, 끝, 기울기)]을 돌려준다."""
    n = len(y)
    cost = _seg_cost_table(y)
    INF = float("inf")
    # dp[k][j] = 앞 j개를 직선 k개로 나눴을 때 최소 오차
    dp = [[INF] * (n + 1) for _ in range(MAX_SEGS + 1)]
    back = [[-1] * (n + 1) for _ in range(MAX_SEGS + 1)]
    dp[0][0] = 0.0
    best = None
    for k in range(1, MAX_SEGS + 1):
        for j in range(k * MIN_SEG, n + 1):
            for i in range((k - 1) * MIN_SEG, j - MIN_SEG + 1):
                if dp[k - 1][i] < INF:
                    c = dp[k - 1][i] + cost(i, j)[0]
                    if c < dp[k][j]:
                        dp[k][j], back[k][j] = c, i
        if dp[k][n] < INF:
            sse = max(dp[k][n], 1e-12)
            bic = n * np.log(sse / n) + 3 * k * np.log(n)
            if best is None or bic < best[0]:
                segs, j = [], n
                for kk in range(k, 0, -1):
                    i = back[kk][j]
                    segs.append((i, j))
                    j = i
                best = (bic, segs[::-1])
    return [(i, j, cost(i, j)[1]) for i, j in best[1]]


def onset_cp(r):
    if r.max() <= 0 or len(r) < 2 * MIN_SEG:
        return None
    y = np.log(r.values + 0.01 * r.max())
    # 연 30% 이상 오르는 직선 구간 중 R이 실제로 가장 많이 늘어난 구간 (방법 1과 같은 기준)
    # 기울기만 보면 데이터 맨 앞의 아주 작은 값(1편 -> 3편)이 '가장 가파르다'고 잡히기 때문
    up = [(r.iloc[j - 1] - r.iloc[i], i) for i, j, slope in segment(y) if slope * 12 >= np.log(1 + GROWTH)]
    return r.index[max(up)[1]] if up else None


# ---------- 방법 3: 교차상관 ----------
def yoy_growth(r):
    eps = 0.01 * r.max() if r.max() > 0 else 1.0
    return (np.log(r + eps) - np.log(r.shift(12) + eps)).dropna()


def ccf(up, down):
    best_k, best_r, r0 = None, -np.inf, np.nan
    for k in CCF_RANGE:
        j = pd.concat([up.shift(k), down], axis=1).dropna()  # 앞선 지표를 k개월 뒤로 민다
        if len(j) < 24 or j.iloc[:, 0].std() == 0 or j.iloc[:, 1].std() == 0:
            continue
        c = j.iloc[:, 0].corr(j.iloc[:, 1])
        if k == 0:
            r0 = c
        if c > best_r:
            best_k, best_r = k, c
    return best_k, (None if best_k is None else round(best_r, 2)), round(r0, 2)


# ---------- 방법 4: 그랜저 인과 ----------
def stationary(s):
    z = (np.log1p(s) - np.log1p(s.shift(12))).dropna()
    if z.std() == 0:
        return None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureWarning)  # statsmodels 버전 안내 메시지 숨김
        adf_p = adfuller(z, autolag="AIC")[1]
    if adf_p > 0.05:  # 아직 추세가 남아 있으면 한 번 더 차분
        z = z.diff().dropna()
    return z


def granger(up, down):
    a, b = stationary(up), stationary(down)
    if a is None or b is None:
        return None, None
    j = pd.concat([b, a], axis=1).dropna()  # [결과, 원인] 순서
    if len(j) < 4 * GRANGER_MAXLAG or j.std().min() == 0:
        return None, None
    with warnings.catch_warnings(), contextlib.redirect_stdout(io.StringIO()):
        warnings.simplefilter("ignore")
        res = grangercausalitytests(j.values, maxlag=GRANGER_MAXLAG)
    p = {lag: res[lag][0]["ssr_ftest"][1] for lag in res}
    lag = min(p, key=p.get)
    return lag, p[lag]


def to_period(v):
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else pd.Period(v, freq="M")


def months_between(a, b):
    return None if a is None or b is None else (b - a).n


def main():
    series = load_series()
    kw = load_keywords()[["ingredient_id", "name_ko", "group"]]
    smooth_s, onset_rows = {}, []
    for (ing, src), s in series.items():
        r = smooth(s, src)
        smooth_s[(ing, src)] = r
        oy, oc = onset_yoy(r), onset_cp(r)
        first_yoy = r.index[0] + 12  # 전년 대비를 처음 계산할 수 있는 달
        onset_rows.append({
            "ingredient_id": ing, "source": src,
            "onset_yoy": None if oy is None else str(oy),
            "onset_cp": None if oc is None else str(oc),
            "first_possible": str(first_yoy),
            "censored": oy is not None and oy <= first_yoy,
            "low_volume": is_low_volume(r, src),
        })
    onsets = pd.DataFrame(onset_rows).merge(kw, on="ingredient_id")
    onsets.to_csv(PROCESSED / "onsets.csv", index=False, encoding="utf-8-sig")

    o = {(x.ingredient_id, x.source): x for x in onsets.itertuples()}
    rows = []
    for ing in kw.ingredient_id:
        for up, down in PAIRS:
            if (ing, up) not in smooth_s or (ing, down) not in smooth_s:
                continue
            ou, od = o[(ing, up)], o[(ing, down)]
            k, rk, r0 = ccf(yoy_growth(smooth_s[(ing, up)]), yoy_growth(smooth_s[(ing, down)]))
            glag, gp = granger(series[(ing, up)], series[(ing, down)])
            rows.append({
                "ingredient_id": ing, "upstream": up, "downstream": down,
                "lag_onset_yoy": months_between(to_period(ou.onset_yoy), to_period(od.onset_yoy)),
                "lag_onset_cp": months_between(to_period(ou.onset_cp), to_period(od.onset_cp)),
                "ccf_best_lag": k, "ccf_best_r": rk, "ccf_r_at_0": r0,
                "granger_best_lag": glag,
                "granger_p": None if gp is None else round(gp, 4),
                "granger_p_bonf": None if gp is None else round(min(1.0, gp * GRANGER_MAXLAG), 4),
                "downstream_censored": bool(od.censored),
                "low_volume": bool(ou.low_volume or od.low_volume),
            })
    lag = pd.DataFrame(rows).merge(kw, on="ingredient_id")
    lag.to_csv(PROCESSED / "lead_lag.csv", index=False, encoding="utf-8-sig")

    train = kw[kw.group == "train"].ingredient_id.tolist()
    pd.set_option("display.width", 250)
    print("=== 학습용 성분 시작점 ===")
    print(onsets[onsets.ingredient_id.isin(train)][
        ["ingredient_id", "source", "onset_yoy", "onset_cp", "first_possible", "censored"]].to_string(index=False))
    print("\n=== 학습용 성분 시차 (양수 = 앞 지표가 먼저, 단위: 개월) ===")
    cols = ["ingredient_id", "upstream", "downstream", "lag_onset_yoy", "lag_onset_cp",
            "ccf_best_lag", "ccf_best_r", "ccf_r_at_0", "granger_best_lag", "granger_p", "granger_p_bonf",
            "downstream_censored"]
    print(lag[lag.ingredient_id.isin(train)][cols].to_string(index=False))
    print("\n저장: data/processed/onsets.csv, data/processed/lead_lag.csv")
    plot(train, smooth_s, o)


def plot(ids, smooth_s, o):
    fig, axes = plt.subplots(2, 2, figsize=(13, 7.5), sharex=True)
    for ax, ing in zip(axes.flat, ids):
        for src in SOURCES:
            r = smooth_s.get((ing, src))
            if r is None:
                continue
            ax.plot(r.index.to_timestamp(), r / r.max(), color=COLOR[src], label=LABEL[src])
            on = o[(ing, src)]
            for v, ls in [(on.onset_yoy, "-"), (on.onset_cp, "--")]:
                if to_period(v) is not None:
                    ax.axvline(to_period(v).to_timestamp(), color=COLOR[src], lw=1.4, ls=ls)
        ax.set_title(ing)
        ax.grid(alpha=0.3)
    axes[0, 0].legend(loc="upper left", fontsize=8)
    fig.suptitle("12-month totals scaled to max. Vertical lines = onset (solid: YoY rule, dashed: change point)")
    fig.tight_layout()
    out = PROCESSED / "w4_onsets_train.png"
    fig.savefig(out, dpi=120)
    print(f"그래프 저장: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
