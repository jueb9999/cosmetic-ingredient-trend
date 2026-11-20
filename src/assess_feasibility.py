"""6주차: 후보 성분의 원료 사업 진입 가능성 평가.

두 축으로 본다.
  시장 매력도 = 5주차 점수 + 지금 검색 증가율 + 효능 근거 (정성)
  진입 용이성 = 특허 경쟁(출원 기업 수, 상위 3사 집중도, 대기업 참여) + 규제 + 원료 수급 + 기술 장벽 (정성)

  * 특허 경쟁: 화장품 IPC 특허, 2021-01 ~ 2025-04 출원 (공개가 다 된 기간)
  * 정성 항목: config/feasibility_notes.csv (1 = 불리, 2 = 보통, 3 = 유리, 근거·출처 함께 기록)
  * 각 항목을 0~1로 바꿔 같은 비중으로 평균
"""
import re

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from common import ROOT

PROCESSED = ROOT / "data" / "processed"
ITEMS = sorted((ROOT / "data" / "raw").glob("kipris_items_*.csv"))[-1]
START, END = 20210101, 20250430
CANDIDATES = ["PLANT_PDRN", "SPICULE", "ASTAXANTHIN", "MICROBIOME", "RICE", "RECOMB_COLLAGEN"]
BENCHMARK = ["PDRN"]   # 이미 시장이 열린 성분 (비교 기준)

UNIV = re.compile(r"대학|산학|연구원|연구소|재단|진흥원|센터|국립")
FOREIGN = re.compile(r"인코포레이티드|엘엘씨|게엠베하|리미티드|코포레이션|에스\.에이|비\.브이|가부시키|캄파니|"
                     r"에스에이에스|아게|피엘씨|엔\.브이|씨오\.|아이엔씨")
CORP = re.compile(r"주식회사|\(주\)|㈜|유한|회사|코리아|바이오|코스|랩|팜|컴퍼니|홀딩스|제약|화장품")
BIG = {"브랜드사", "ODM"}

OFFSET = {"RECOMB_COLLAGEN": (-8, -14)}   # 겹치는 레이블 위치 조정
INK, INK2, GRID, BLUE, GRAY = "#0b0b0b", "#52514e", "#e4e3df", "#2a78d6", "#8a8984"


def applicant_kind(name, types):
    if types.get(name) == "대학·연구소" or UNIV.search(name):
        return "univ"
    if types.get(name) == "해외" or FOREIGN.search(name):
        return "foreign"
    if CORP.search(name) or name in types:
        return "corp"
    return "person"


def patent_competition(ings):
    items = pd.read_csv(ITEMS, encoding="utf-8-sig")
    types = pd.read_csv(ROOT / "config" / "applicant_types.csv", encoding="utf-8-sig")
    tmap = dict(zip(types.applicant.str.strip(), types.type))
    allc = items[items.is_cosmetic_ipc]
    win = allc[(allc.applicationDate >= START) & (allc.applicationDate <= END)]
    ap = win.assign(applicant=win.applicantName.fillna("").str.split("|")).explode("applicant")
    ap["applicant"] = ap.applicant.str.strip()
    ap["kind"] = ap.applicant.map(lambda x: applicant_kind(x, tmap))
    ap["type"] = ap.applicant.map(tmap)

    # 성분별로 각 기업이 처음 출원한 해 -> 최근 2년(2023~) 새로 들어온 기업 비율
    first = (allc.assign(applicant=allc.applicantName.fillna("").str.split("|")).explode("applicant")
             .assign(applicant=lambda d: d.applicant.str.strip())
             .groupby(["ingredient_id", "applicant"]).applicationDate.min())

    rows = []
    for ing in ings:
        g = ap[ap.ingredient_id == ing]
        corp = g[g.kind.isin(["corp", "foreign"])]
        vc = corp.applicant.value_counts()
        firsts = first.loc[ing].reindex(vc.index)
        rows.append({
            "ingredient_id": ing,
            "patents": win[win.ingredient_id == ing].applicationNumber.nunique(),
            "companies": int(vc.size),
            "top3_share": round(vc.head(3).sum() / max(vc.sum(), 1), 2),
            "new_company_share": round(float((firsts >= 20230101).mean()) if vc.size else np.nan, 2),
            "univ_share": round(float((g.kind == "univ").mean()), 2),
            "foreign_share": round(float((g.kind == "foreign").mean()), 2),
            "big_players": int(g[g.type.isin(BIG)].applicant.nunique()),
            "big_player_names": ", ".join(sorted(set(g[g.type.isin(BIG)].applicant))),
            "top_companies": ", ".join(f"{k}({v})" for k, v in vc.head(4).items()),
        })
    return pd.DataFrame(rows)


def main():
    ings = CANDIDATES + BENCHMARK
    comp = patent_competition(ings)
    notes = pd.read_csv(ROOT / "config" / "feasibility_notes.csv", encoding="utf-8-sig")
    sc = pd.read_csv(PROCESSED / "scores.csv", encoding="utf-8-sig")
    d = (comp.merge(notes, on="ingredient_id")
         .merge(sc[["ingredient_id", "name_ko", "score", "status", "search_mom", "search_level", "proc_mom"]],
                on="ingredient_id"))

    # 0~1로 바꾸기. 후보끼리 비교하는 순위 지표는 후보 6개 안에서 백분위로 (비교 기준 PDRN 제외)
    cand = d.ingredient_id.isin(CANDIDATES)

    def pct(col, higher_is_better=True):
        ref = d.loc[cand, col]
        f = (lambda v: (ref <= v).mean()) if higher_is_better else (lambda v: (ref >= v).mean())
        return d[col].map(f)

    d["a_score"] = pct("score")
    d["a_search"] = pct("search_mom")
    d["a_evidence"] = (d.evidence - 1) / 2
    d["e_companies"] = pct("companies", higher_is_better=False)
    d["e_big"] = pct("big_players", higher_is_better=False)
    d["e_concentration"] = pct("top3_share", higher_is_better=False)
    for c in ["regulation", "supply", "tech"]:
        d[f"e_{c}"] = (d[c] - 1) / 2
    A = ["a_score", "a_search", "a_evidence"]
    E = ["e_companies", "e_concentration", "e_big", "e_regulation", "e_supply", "e_tech"]
    d["attractiveness"] = d[A].mean(axis=1).round(2)
    d["ease"] = d[E].mean(axis=1).round(2)

    def quadrant(r):
        hi_a, hi_e = r.attractiveness >= 0.5, r.ease >= 0.5
        return {(True, True): "우선 검토", (True, False): "매력 있지만 진입 어려움",
                (False, True): "쉽지만 매력 낮음", (False, False): "보류"}[(hi_a, hi_e)]

    d["quadrant"] = d.apply(quadrant, axis=1)
    d.loc[~cand, "quadrant"] = "비교 기준"

    # 민감도: 항목을 하나씩 빼고 다시 계산했을 때 같은 칸에 남는 횟수 (전체 9번)
    same = pd.Series(0, index=d.index)
    for drop in A + E:
        t = d.copy()
        t["attractiveness"] = t[[c for c in A if c != drop]].mean(axis=1)
        t["ease"] = t[[c for c in E if c != drop]].mean(axis=1)
        same += (t.apply(quadrant, axis=1) == d.quadrant).astype(int)
    d["robust"] = same.astype(str) + f"/{len(A + E)}"
    d.loc[~cand, "robust"] = "-"
    edge = cand & (((d.attractiveness - 0.5).abs() < 0.05) | ((d.ease - 0.5).abs() < 0.05))
    d.loc[edge, "quadrant"] += " (경계)"
    d = d.sort_values(["attractiveness"], ascending=False)
    cols = ["ingredient_id", "name_ko", "quadrant", "robust", "attractiveness", "ease", "score", "search_mom", "proc_mom",
            "evidence", "patents", "companies", "top3_share", "new_company_share", "univ_share", "foreign_share",
            "big_players", "regulation", "supply", "tech", "top_companies", "big_player_names",
            "regulation_basis", "supply_basis", "tech_basis", "evidence_basis", "market_notes", "sources"]
    d[cols].to_csv(PROCESSED / "feasibility.csv", index=False, encoding="utf-8-sig")
    plot(d)

    pd.set_option("display.width", 220)
    print(d[["ingredient_id", "quadrant", "robust", "attractiveness", "ease", "a_score", "a_search", "a_evidence",
             "e_companies", "e_concentration", "e_big", "e_regulation", "e_supply", "e_tech"]].round(2).to_string(index=False))
    print()
    print(d[["ingredient_id", "patents", "companies", "top3_share", "new_company_share", "univ_share",
             "foreign_share", "big_players", "top_companies"]].to_string(index=False))
    print("\n저장: data/processed/feasibility.csv, w6_feasibility.png")


def plot(d):
    fig, ax = plt.subplots(figsize=(8, 6.5))
    fig.patch.set_facecolor("#fcfcfb")
    ax.set_facecolor("#fcfcfb")
    ax.axvline(0.5, color=GRID, lw=1.2)
    ax.axhline(0.5, color=GRID, lw=1.2)
    for x, y, t in [(0.98, 0.98, "Priority"), (0.02, 0.98, "Attractive but hard to enter"),
                    (0.98, 0.02, "Easy but less attractive"), (0.02, 0.02, "Hold")]:
        ax.text(x, y, t, transform=ax.transAxes, ha="right" if x > 0.5 else "left",
                va="top" if y > 0.5 else "bottom", fontsize=8.5, color=INK2, style="italic")
    for _, r in d.iterrows():
        bench = r.quadrant == "비교 기준"
        ax.scatter(r.ease, r.attractiveness, s=60 + r.patents * 1.5, color=GRAY if bench else BLUE,
                   edgecolor="#fcfcfb", linewidth=2, zorder=3)
        ax.annotate(r.ingredient_id + (" (benchmark)" if bench else ""), (r.ease, r.attractiveness),
                    xytext=OFFSET.get(r.ingredient_id, (8, 6)), textcoords="offset points", fontsize=8.5,
                    color=INK, ha="right" if r.ingredient_id in OFFSET else "left")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xlabel("Ease of entry (patent competition, regulation, supply, tech barrier)", fontsize=8.5, color=INK2)
    ax.set_ylabel("Market attractiveness (W5 score, search growth, evidence)", fontsize=8.5, color=INK2)
    ax.set_title("Raw-material entry feasibility  (bubble size = cosmetic patents 2021-01~2025-04)",
                 fontsize=10, color=INK, loc="left")
    for s in ["top", "right"]:
        ax.spines[s].set_visible(False)
    for s in ["left", "bottom"]:
        ax.spines[s].set_color(INK2)
    ax.tick_params(colors=INK2, labelsize=8)
    fig.tight_layout()
    fig.savefig(PROCESSED / "w6_feasibility.png", dpi=150, facecolor=fig.get_facecolor())


if __name__ == "__main__":
    main()
