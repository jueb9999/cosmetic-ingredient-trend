"""7주차: 결과 대시보드.

실행:  streamlit run app.py
분석 스크립트(src/)가 만든 data/processed/ 결과 파일만 읽는다. API 키가 필요 없다.
"""
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
P = ROOT / "data" / "processed"
RAW = ROOT / "data" / "raw"

TITLE = "선행지표 기반 화장품 성분 트렌드 예측과 원료 사업 진입 전략"
# 기본 검증 팔레트 (순서 고정, 순환하지 않음)
PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
GRAY, INK2, GRID = "#8a8984", "#52514e", "#e4e3df"
STAGES = ["논문", "특허", "화장품 검색", "시술 검색"]
SOURCE_STAGE = {"pubmed": "논문", "kipris_cosmetic": "특허", "naver": "화장품 검색", "naver_procedure": "시술 검색"}
PATH_STAGES = ["시술 검색", "시술 제품사 특허", "원료사 특허", "ODM 특허", "브랜드사 특허", "화장품 검색"]
PROC_KO = {"Rejuran (PDRN)": "리쥬란", "Juvelook (PDLLA)": "쥬베룩", "Re2O (ECM)": "리투오", "NAD drip": "NAD 주사"}
SRC_KO = {"pubmed": "논문", "kipris_cosmetic": "화장품 특허", "kipris_all": "전체 특허"}
GROUP_KO = {"train": "학습", "candidate": "후보"}

st.set_page_config(page_title="성분 트렌드 선행지표", layout="wide")


# ---------- 데이터 ----------
@st.cache_data
def load_csv(name):
    return pd.read_csv(P / name, encoding="utf-8-sig")


@st.cache_data
def load_trend():
    t = load_csv("trend_long.csv")
    t = t[t.source.isin(SOURCE_STAGE)].copy()
    t["지표"] = t.source.map(SOURCE_STAGE)
    scan_files = sorted(RAW.glob("naver_scan_2*.csv"))
    if scan_files:  # 7주차 새 후보 검색량
        meta = pd.read_csv(ROOT / "config" / "scan_keywords.csv", encoding="utf-8-sig")
        s = pd.read_csv(scan_files[-1], encoding="utf-8-sig")
        s = s.merge(meta[["ingredient_id", "stage"]], on="ingredient_id", suffixes=("_x", ""))
        s["지표"] = np.where(s.stage == "procedure", "시술 검색", "화장품 검색")
        s["ingredient_id"] = s.ingredient_id.replace({"NAD_PROC": "NAD", "PDLLA_PROC": "PDLLA", "ECM_PROC": "ECM"})
        s["name_ko"] = s.ingredient_id.map(dict(zip(meta.ingredient_id, meta.name_ko)))
        s = s.rename(columns={"value_scaled": "value"})
        s["group"], s["provisional"] = "new", False
        t = pd.concat([t, s[["ingredient_id", "name_ko", "group", "지표", "month", "value", "provisional"]]])
    t["month"] = pd.to_datetime(t["month"])
    return t


def smooth(df, window):
    if window <= 1:
        return df
    out = []
    for _, g in df.groupby(["ingredient_id", "지표"]):
        g = g.sort_values("month").copy()
        g["value"] = g.value.rolling(window).mean()
        out.append(g.dropna(subset=["value"]))
    return pd.concat(out)


def color_scale(domain):
    return alt.Scale(domain=list(domain), range=PALETTE[:len(domain)])


# ---------- 화면 ----------
st.title(TITLE)
st.caption("PDRN이 뜨기 전에 무엇이 먼저 움직였는지 찾고, 같은 신호로 다음 성분을 찾는 프로젝트 · "
           "데이터: PubMed 논문, KIPRIS 특허, 네이버 데이터랩 검색량 (2026년 10월까지)")

tabs = st.tabs(["한눈에 보기", "성분 추이", "시차 분석", "점수와 백테스트", "원료 사업 진입", "PDRN 다음 후보"])

# 1. 요약
with tabs[0]:
    c = st.columns(4)
    c[0].metric("분석 성분", "20 + 새 후보 9", help="1주차 20개(학습 4, 후보 16) + 7주차 새 후보 9개")
    c[1].metric("시술이 화장품 검색보다 먼저", "4 / 4", "1~3년 앞섬", help="PDRN, 엑소좀, 스피큘, 글루타치온")
    c[2].metric("H2 점수 백테스트 순위상관", "0.10", "단순 추세 0.19보다 낮음", delta_color="off")
    c[3].metric("1주차 20개 중 '유행 지남'", f"{(load_csv('scores.csv').status == '유행 지남').sum()}개")
    st.subheader("핵심 결과")
    st.markdown("""
1. **성분이 뜨는 길은 두 가지예요.**
   - 나이아신아마이드·레티놀은 *특허 → (2~6년 뒤) 소비자* 순서였어요.
   - PDRN·엑소좀·스피큘·글루타치온은 *피부과 시술 → (1~3년 뒤) 화장품 검색 → 원료사·브랜드 특허* 순서였어요.
2. **특허·논문 증가만으로 다음 유행을 맞히기는 어려웠어요.** 과거 시점 백테스트에서 예측력이 거의 없었어요. 그래서 점수는 후보를 좁히는 거름망으로만 써요.
3. **처음 고른 20개 성분 대부분은 이미 정점을 지났어요.** 그래서 업계에서 거론되는 새 성분 9개를 추가로 조사했어요('PDRN 다음 후보' 탭).
4. **PDRN 다음 후보 (2026년 10월 기준)**
   - **아젤라산:** 검색이 꾸준히 올라 PDRN이 뜨기 직전 모습과 가장 닮았어요. 다만 처방약 관심이 섞여 있어요.
   - **NAD·NMN:** 2026년 여름에 급등했다가 조정 중이에요.
   - **리투오(ECM):** 시술 검색이 리쥬란 초기처럼 오르고 있어요. 시술 경로를 따른다면 1~3년 뒤 화장품 쪽이 뒤따를 수 있어요.
""")
    st.info("이 대시보드의 숫자는 검색·특허·논문 데이터로 본 '신호'이지 판매량이 아니에요. 한계는 README의 '알아둘 한계'에 정리돼 있어요.")

# 2. 성분 추이
with tabs[1]:
    t = load_trend()
    names = t.drop_duplicates("ingredient_id").set_index("ingredient_id").name_ko.to_dict()
    ids = sorted(names, key=lambda i: (i not in ("PDRN", "NAD", "AZELAIC", "ECM"), names[i]))
    left, right = st.columns([3, 1])
    sel = left.multiselect("성분 (최대 4개)", ids, default=["PDRN", "AZELAIC"], max_selections=4,
                           format_func=lambda i: names[i])
    win = right.select_slider("이동평균", options=[1, 3, 6, 12], value=3,
                              format_func=lambda v: "원자료" if v == 1 else f"{v}개월")
    a, b = st.columns([3, 1])
    stages = a.multiselect("지표", STAGES, default=STAGES)
    norm = b.toggle("성분마다 최댓값 = 100", value=len(sel) > 1,
                    help="검색량이 큰 성분(PDRN 등)과 작은 성분을 함께 볼 때 켜면 모양을 비교할 수 있어요.")
    d = t[t.ingredient_id.isin(sel) & t["지표"].isin(stages) & (t.month >= "2015-01-01")]
    d = smooth(d, win)
    if d.empty:
        st.warning("선택한 성분에 해당 지표 데이터가 없어요.")
    else:
        d = d.assign(성분=d.ingredient_id.map(names), 원래값=d.value)
        if norm:
            d["value"] = d.value / d.groupby(["ingredient_id", "지표"]).value.transform("max").replace(0, np.nan) * 100
        sel_names = [names[i] for i in sel]
        hover = alt.selection_point(fields=["month"], nearest=True, on="pointerover", empty=False)
        base = alt.Chart(d).encode(
            x=alt.X("month:T", title=None, axis=alt.Axis(format="%Y", tickCount="year")),
            y=alt.Y("value:Q", title="최댓값 = 100" if norm else None),
            color=alt.Color("성분:N", scale=color_scale(sel_names), legend=alt.Legend(orient="top", title=None)),
        )
        lines = base.mark_line(strokeWidth=2)
        pts = base.mark_point(size=50, filled=True).encode(
            opacity=alt.condition(hover, alt.value(1), alt.value(0)),
            tooltip=[alt.Tooltip("성분:N"), alt.Tooltip("지표:N"), alt.Tooltip("month:T", title="월", format="%Y년 %m월"),
                     alt.Tooltip("원래값:Q", title="값", format=",.1f")]).add_params(hover)
        rule = alt.Chart(d).mark_rule(color=GRAY).encode(x="month:T").transform_filter(hover)
        chart = (lines + pts + rule).properties(height=160).facet(
            row=alt.Row("지표:N", sort=STAGES, title=None, header=alt.Header(labelAngle=0, labelAlign="left"))
        ).resolve_scale(y="independent")
        st.altair_chart(chart, width="stretch")
        st.caption("지표마다 단위가 달라 칸을 나눴어요. 논문·특허 = 월 건수, 검색 = 히알루론산 평균 100 기준 지수. "
                   "특허는 출원 후 18개월 뒤 공개되므로 2025년 5월 이후 값은 실제보다 적어요. "
                   "7주차 새 후보는 검색량만 모았어요.")

# 3. 시차 분석
with tabs[2]:
    st.subheader("시술 → 화장품 확산 순서")
    st.caption("T25 = 2016년 이후 늘어난 양이 누적 25%에 도달한 달. 먼저 도달할수록 먼저 움직인 단계예요.")
    pp = load_csv("procedure_path_onsets.csv")
    cols = ["name_ko", "시술 검색", "화장품 검색", "원료사 특허", "브랜드사 특허", "ODM 특허", "순서"]
    st.dataframe(pp[cols].rename(columns={"name_ko": "성분"}), hide_index=True, width="stretch")

    yr = load_csv("procedure_path_yearly.csv")
    kw = load_csv("trend_long.csv").drop_duplicates("ingredient_id").set_index("ingredient_id").name_ko
    opts = [i for i in ["PDRN", "EXOSOME", "SPICULE", "GLUTATHIONE", "NIACINAMIDE", "RETINOL", "CICA", "PEPTIDE"]
            if i in set(yr.ingredient_id)]
    ing = st.selectbox("성분 선택", opts, format_func=lambda i: kw.get(i, i))
    y = yr[(yr.ingredient_id == ing) & yr.year.between(2016, 2025)].copy()
    y["최댓값 대비"] = y.value / y.groupby("stage").value.transform("max").replace(0, np.nan)
    y = y.dropna(subset=["최댓값 대비"])
    y["종류"] = np.where(y.stage.str.contains("검색"), "검색량", "특허")
    y["연도"] = pd.to_datetime(y.year.astype(str))
    shown = [s for s in PATH_STAGES if s in set(y.stage)]
    band = alt.Chart(pd.DataFrame({"a": [pd.Timestamp("2024-07-01")], "b": [pd.Timestamp("2025-06-30")]})).mark_rect(
        color=GRID, opacity=0.7).encode(x="a:T", x2="b:T")
    line = alt.Chart(y).mark_line(point=alt.OverlayMarkDef(size=40)).encode(
        x=alt.X("연도:T", title=None, axis=alt.Axis(format="%Y", tickCount="year")),
        y=alt.Y("최댓값 대비:Q", title="단계별 최댓값 = 1", scale=alt.Scale(domain=[0, 1.05])),
        color=alt.Color("stage:N", title=None, scale=color_scale(shown), sort=shown, legend=alt.Legend(orient="top")),
        strokeDash=alt.StrokeDash("종류:N", title=None, scale=alt.Scale(domain=["검색량", "특허"], range=[[1, 0], [5, 3]]),
                                  legend=None),
        strokeWidth=alt.condition(alt.datum.종류 == "검색량", alt.value(3), alt.value(1.8)),
        tooltip=[alt.Tooltip("stage:N", title="단계"), alt.Tooltip("year:Q", title="연도"),
                 alt.Tooltip("value:Q", title="값", format=",.1f")])
    st.altair_chart((band + line).properties(height=340), width="stretch")
    st.caption("실선 = 검색량, 점선 = 출원인 유형별 특허. 회색 = 특허가 아직 덜 공개된 기간. "
               "나이아신아마이드·레티놀·시카는 시술이 없는 비교군이에요.")

    st.subheader("논문·특허 → 검색 시차 (학습 성분 4개)")
    ll = load_csv("lead_lag.csv")
    ll = ll[ll.downstream == "naver"].assign(upstream=lambda x: x.upstream.map(SRC_KO).fillna(x.upstream),
                                             downstream_censored=lambda x: x.downstream_censored.map({True: "예", False: "아니오"}))
    ll = ll[["name_ko", "upstream", "lag_onset_yoy", "ccf_best_lag", "ccf_best_r", "granger_p_bonf", "downstream_censored"]]
    st.dataframe(ll.rename(columns={"name_ko": "성분", "upstream": "앞 지표", "lag_onset_yoy": "시작점 시차(월)",
                                    "ccf_best_lag": "교차상관 시차(월)", "ccf_best_r": "상관계수",
                                    "granger_p_bonf": "그랜저 p값(보정)", "downstream_censored": "검색 시작 잘림"}),
                 hide_index=True, width="stretch")
    st.caption("시차가 양수면 논문·특허가 먼저예요. 나이아신아마이드·레티놀은 앞섰고, PDRN은 검색이 먼저였어요.")

# 4. 점수와 백테스트
with tabs[3]:
    sc = load_csv("scores.csv")
    st.subheader("H2 점수: 논문·특허는 오르는데 검색은 아직 낮은 성분")
    show = sc[["rank", "name_ko", "group", "score", "status", "pub_pct", "pat_pct", "room_pct", "search_from_peak"]]
    show = show.assign(group=show.group.map(GROUP_KO))
    st.dataframe(show.rename(columns={"rank": "순위", "name_ko": "성분", "group": "구분", "score": "점수", "status": "판정",
                                      "pub_pct": "논문 모멘텀", "pat_pct": "특허 모멘텀", "room_pct": "검색 여지",
                                      "search_from_peak": "정점 대비 검색"}),
                 hide_index=True, width="stretch",
                 column_config={"점수": st.column_config.ProgressColumn(min_value=0, max_value=1, format="%.2f")})
    st.subheader("백테스트: 과거 시점 점수가 3년 뒤 검색 증가를 맞혔나?")
    bt = load_csv("score_backtest.csv")
    names_bt = ["H2 점수", "위쪽 신호만", "단순 추세(검색 증가율)"]
    bt = bt[bt.variant.isin(names_bt)].assign(variant=lambda x: x.variant.replace({"위쪽 신호만": "논문·특허 신호만"}))
    bt["asof"] = pd.to_datetime(bt["asof"])
    band = alt.Chart(pd.DataFrame({"y": [-0.44], "y2": [0.44]})).mark_rect(color=GRID, opacity=0.7).encode(y="y:Q", y2="y2:Q")
    order = ["H2 점수", "논문·특허 신호만", "단순 추세(검색 증가율)"]
    line = alt.Chart(bt).mark_line(point=True, strokeWidth=2).encode(
        x=alt.X("asof:T", title="기준 시점", axis=alt.Axis(format="%Y", tickCount="year")),
        y=alt.Y("spearman:Q", title="순위상관", scale=alt.Scale(domain=[-1, 1])),
        color=alt.Color("variant:N", title=None, scale=alt.Scale(domain=order, range=[PALETTE[1], PALETTE[0], INK2]),
                        legend=alt.Legend(orient="top")),
        tooltip=[alt.Tooltip("variant:N", title="방법"), alt.Tooltip("asof:T", title="기준 시점", format="%Y년 %m월"),
                 alt.Tooltip("spearman:Q", title="순위상관", format=".2f"), alt.Tooltip("top5:N", title="상위 5개")])
    st.altair_chart((band + line).properties(height=300), width="stretch")
    st.caption("회색 띠 = 통계적으로 의미 없음(|순위상관| < 0.44, 성분 20개). 세 방법 모두 대부분 띠 안에 있어요.")

# 5. 원료 사업 진입
with tabs[4]:
    fe = load_csv("feasibility.csv")
    st.subheader("시장 매력도 × 진입 용이성")
    fe["구분"] = np.where(fe.quadrant == "비교 기준", "비교 기준", "후보")
    pts = alt.Chart(fe).mark_circle(stroke="#fcfcfb", strokeWidth=2, opacity=1).encode(
        x=alt.X("ease:Q", title="진입 용이성 →", scale=alt.Scale(domain=[0, 1]), axis=alt.Axis(tickCount=5)),
        y=alt.Y("attractiveness:Q", title="시장 매력도 →", scale=alt.Scale(domain=[0, 1]), axis=alt.Axis(tickCount=5)),
        size=alt.Size("patents:Q", title="화장품 특허 수", legend=None, scale=alt.Scale(range=[80, 600])),
        color=alt.Color("구분:N", title=None, scale=alt.Scale(domain=["후보", "비교 기준"], range=[PALETTE[0], GRAY]),
                        legend=alt.Legend(orient="top")),
        tooltip=[alt.Tooltip("name_ko:N", title="성분"), alt.Tooltip("quadrant:N", title="판정"),
                 alt.Tooltip("attractiveness:Q", title="매력도"), alt.Tooltip("ease:Q", title="진입 용이성"),
                 alt.Tooltip("companies:Q", title="출원 기업 수"), alt.Tooltip("top_companies:N", title="주요 출원인")])
    left_label = fe.ingredient_id.isin(["RECOMB_COLLAGEN"])   # 이웃 점과 이름이 겹치는 성분은 왼쪽에 표시
    labels = alt.layer(
        alt.Chart(fe[~left_label]).mark_text(align="left", dx=12, dy=-10, fontSize=12).encode(
            x="ease:Q", y="attractiveness:Q", text="name_ko:N"),
        alt.Chart(fe[left_label]).mark_text(align="right", dx=-10, dy=-10, fontSize=12).encode(
            x="ease:Q", y="attractiveness:Q", text="name_ko:N"))
    quad = pd.DataFrame({"x": [0.02, 0.98, 0.02, 0.98], "y": [0.98, 0.98, 0.02, 0.02],
                         "t": ["매력 있지만 진입 어려움", "우선 검토", "보류", "쉽지만 매력 낮음"],
                         "align": ["left", "right", "left", "right"]})
    qtext = alt.layer(*[alt.Chart(quad[quad["align"] == al]).mark_text(fontStyle="italic", color=INK2, fontSize=11,
                                                                         align=al).encode(x="x:Q", y="y:Q", text="t:N")
                        for al in ("left", "right")])
    rules = alt.Chart(pd.DataFrame({"v": [0.5]})).mark_rule(color="#c3c2b7")
    st.altair_chart((rules.encode(x="v:Q") + rules.encode(y="v:Q") + qtext + pts + labels).properties(height=440),
                    width="stretch")
    pick = st.selectbox("성분 근거 보기", fe.ingredient_id, format_func=lambda i: fe.set_index("ingredient_id").name_ko[i])
    r = fe.set_index("ingredient_id").loc[pick]
    a, b = st.columns(2)
    a.markdown(f"**판정:** {r.quadrant} (항목 하나씩 빼도 같은 칸: {r.robust})\n\n"
               f"**특허 경쟁:** 출원 기업 {r.companies}곳, 상위 3사 비중 {r.top3_share:.0%}, "
               f"2023년 이후 신규 {r.new_company_share:.0%}\n\n**주요 출원인:** {r.top_companies}")
    b.markdown(f"**규제({r.regulation}/3):** {r.regulation_basis}\n\n**수급({r.supply}/3):** {r.supply_basis}\n\n"
               f"**기술({r.tech}/3):** {r.tech_basis}\n\n**근거({r.evidence}/3):** {r.evidence_basis}")
    st.markdown(f"**시장 메모:** {r.market_notes}")
    st.markdown("**출처:** " + " · ".join(f"[{i + 1}]({u.strip()})" for i, u in enumerate(str(r.sources).split("|"))))

# 6. PDRN 다음 후보
with tabs[5]:
    nc = load_csv("next_candidates.csv")
    path = load_csv("pdrn_path.csv")
    st.subheader("지금 모습이 'PDRN이 뜨기 직전'과 닮은 성분은?")
    st.markdown("PDRN 화장품 검색은 2020~2022년에 낮은 수준(10 안팎)에서 **꾸준히** 오르다가 2023년에 폭발했어요. "
                "같은 모양인지 네 가지로 봤어요: 검색 수준, 1년 증가율, 꾸준함(전년 같은 달보다 높은 달 비율), 정점 대비 지금.")

    # 왼쪽: 지금 위치 vs PDRN이 지나온 길
    nc["구분"] = np.where(nc.new_candidate, "7주차 새 후보", "1주차 20개")
    nc["x"] = nc.level.clip(lower=0.05)
    nc["y"] = (nc.growth * 100).clip(-60, 300)
    nc["강조"] = nc.judgement.isin(["PDRN 직전과 닮음", "급등 후 조정", "아직 작음"])
    nc["짧은 이름"] = nc.name_ko.str.replace(r"\(.*\)", "", regex=True).str.strip()
    nc.loc[nc.growth * 100 > 300, "짧은 이름"] += nc.growth.map(lambda g: f" (+{g:.0%})")
    # 이름이 겹치는 성분: (정렬, 세로 이동 %p)
    place = {"COPPER_PEPTIDE": ("right", 0), "RICE": ("left", 12), "PDLLA": ("right", 0), "ECM": ("left", -12)}
    nc["정렬"] = nc.ingredient_id.map(lambda i: place.get(i, ("left", 0))[0])
    nc["ly"] = nc.y + nc.ingredient_id.map(lambda i: place.get(i, ("left", 0))[1])
    path = path.assign(x=path.level.clip(lower=0.05), y=(path.growth * 100).clip(-60, 300),
                       label=path.year.astype(str) + "년")
    xs = alt.Scale(type="log", domain=[0.05, 200])
    ys = alt.Scale(domain=[-60, 320])
    pdrn_line = alt.Chart(path).mark_line(color=GRAY, strokeWidth=2).encode(
        x=alt.X("x:Q", scale=xs, title="최근 12개월 검색 수준 (히알루론산 = 100, 로그 눈금)"),
        y=alt.Y("y:Q", scale=ys, title="1년 전보다 늘어난 비율 (%)"), order="year:O")
    pdrn_pts = pdrn_line.mark_circle(color=GRAY, size=50).encode(
        tooltip=[alt.Tooltip("label:N", title="PDRN"), alt.Tooltip("level:Q", title="검색 수준", format=".1f"),
                 alt.Tooltip("growth:Q", title="1년 증가율", format="+.0%")])
    pdrn_txt = alt.Chart(path[path.year % 2 == 0]).mark_text(dx=6, dy=12, align="left", fontSize=10, color=INK2).encode(
        x=alt.X("x:Q", scale=xs), y=alt.Y("y:Q", scale=ys), text="label:N")
    cand = alt.Chart(nc[nc.ingredient_id != "PDRN"]).mark_circle(size=90, stroke="#fcfcfb", strokeWidth=1.5).encode(
        x=alt.X("x:Q", scale=xs), y=alt.Y("y:Q", scale=ys),
        color=alt.Color("구분:N", title=None, scale=alt.Scale(domain=["7주차 새 후보", "1주차 20개"], range=PALETTE[:2]),
                        legend=alt.Legend(orient="top")),
        opacity=alt.condition(alt.datum.강조, alt.value(1), alt.value(0.3)),
        tooltip=[alt.Tooltip("name_ko:N", title="성분"), alt.Tooltip("judgement:N", title="판정"),
                 alt.Tooltip("level:Q", title="검색 수준", format=".1f"),
                 alt.Tooltip("growth:Q", title="1년 증가율", format="+.0%"),
                 alt.Tooltip("steady:Q", title="꾸준함", format=".2f")])
    hot = nc[nc.강조 & (nc.ingredient_id != "PDRN")]
    cand_txt = alt.layer(*[alt.Chart(hot[hot["정렬"] == al]).mark_text(dx=9 if al == "left" else -9, align=al, fontSize=12)
                           .encode(x=alt.X("x:Q", scale=xs), y=alt.Y("ly:Q", scale=ys), text="짧은 이름:N")
                           for al in ("left", "right")])
    ref = alt.Chart(pd.DataFrame({"y": [30]})).mark_rule(color=INK2, strokeDash=[4, 3]).encode(y=alt.Y("y:Q", scale=ys))
    left_chart = (ref + pdrn_line + pdrn_pts + pdrn_txt + cand + cand_txt).properties(
        height=420, title="회색 선 = PDRN이 지나온 길 (매년 10월), 점선 = 연 30% 증가")

    # 오른쪽: 스킨부스터 시술 검색량
    t = load_trend()
    proc_names = {"PDRN": "리쥬란 (PDRN)", "PDLLA": "쥬베룩 (PDLLA)", "ECM": "리투오 (ECM)", "NAD": "NAD 주사"}
    pr = t[(t["지표"] == "시술 검색") & t.ingredient_id.isin(proc_names) & (t.month >= "2017-10-01")]
    pr = smooth(pr, 3)
    pr = pr[pr.month >= "2018-01-01"].assign(시술=lambda x: x.ingredient_id.map(proc_names))
    order = list(proc_names.values())
    right_chart = alt.Chart(pr).mark_line(strokeWidth=2.2).encode(
        x=alt.X("month:T", title=None, axis=alt.Axis(format="%Y", tickCount="year")),
        y=alt.Y("value:Q", title="검색 지수 (히알루론산 = 100, 3개월 평균)"),
        color=alt.Color("시술:N", title=None, scale=alt.Scale(domain=order, range=PALETTE[:4]),
                        legend=alt.Legend(orient="top")),
        tooltip=[alt.Tooltip("시술:N"), alt.Tooltip("month:T", title="월", format="%Y년 %m월"),
                 alt.Tooltip("value:Q", title="검색 지수", format=".1f")]).properties(
        height=420, title="스킨부스터 시술 검색량")
    l, r = st.columns(2)
    l.altair_chart(left_chart, width="stretch")
    r.altair_chart(right_chart, width="stretch")

    flt = st.radio("표 보기", ["새 후보만", "전체"], horizontal=True)
    v = nc[nc.new_candidate] if flt == "새 후보만" else nc
    v = v.assign(procedure=v.procedure.map(PROC_KO))
    st.dataframe(v[["name_ko", "judgement", "level", "growth", "steady", "from_peak", "peak_month", "procedure", "proc_growth"]]
                 .rename(columns={"name_ko": "성분", "judgement": "판정", "level": "검색 수준", "growth": "1년 증가율",
                                  "steady": "꾸준함", "from_peak": "정점 대비", "peak_month": "정점 시기",
                                  "procedure": "관련 시술", "proc_growth": "시술 1년 증가율"}),
                 hide_index=True, width="stretch",
                 column_config={"1년 증가율": st.column_config.NumberColumn(format="percent"),
                                "시술 1년 증가율": st.column_config.NumberColumn(format="percent"),
                                "꾸준함": st.column_config.NumberColumn(format="%.2f"),
                                "정점 대비": st.column_config.NumberColumn(format="%.2f"),
                                "검색 수준": st.column_config.NumberColumn(format="%.1f")})
    st.markdown("""
**읽는 법과 주의점**
- **아젤라산**은 검색 증가가 꾸준해요. 다만 검색 대부분이 처방약(아젤리아·피나세아 연고)이에요. 화장품 이름인 '아젤라익애씨드' 검색도 2024년보다 약 10배 늘었어요. 화장품 배합 한도는 식약처 고시 원문으로 확인해야 해요.
- **NAD·NMN**은 2026년 6월에 급등했다가 내려오는 중이에요. 연예인 언급으로 생긴 반짝 유행인지 몇 달 더 지켜봐야 해요.
- **리투오(ECM)**는 화장품이 아니라 인체조직 시술이에요. 시술 검색은 리쥬란 초기처럼 오르고 있지만, 2026년 사체 원료 논란 같은 규제 리스크가 있어요.
- 쥬베룩 시술은 2025년에 정점을 지났어요. 그런데 PDLLA 화장품 검색은 아직 1 수준이에요. PDRN 때(시술 정점 무렵 화장품 검색 10 이상)보다 확산이 약해요. 주사로만 효과를 내는 성분은 바르는 화장품으로 잘 넘어가지 않는 것으로 보여요.
""")
