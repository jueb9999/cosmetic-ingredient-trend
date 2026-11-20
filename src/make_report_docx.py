"""최종 보고서 워드(.docx) 만들기. 웹 보고서와 같은 내용·순서.

실행: python src/make_report_docx.py  ->  docs/final_report.docx  (python-docx 필요)
"""
import re
import sys
from pathlib import Path

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
FIG = ROOT / "data" / "processed"
OUT = ROOT / "docs" / "final_report.docx"

FONT = "맑은 고딕"
ACCENT = RGBColor(0x0B, 0x6E, 0x64)
INK = RGBColor(0x14, 0x1A, 0x21)
MUTED = RGBColor(0x5A, 0x65, 0x73)
LINE = "D5DBE1"
SHADE = "F1F4F6"

doc = Document()
sec = doc.sections[0]
sec.page_width, sec.page_height = Cm(21), Cm(29.7)
sec.left_margin = sec.right_margin = Cm(2.2)
sec.top_margin, sec.bottom_margin = Cm(2.2), Cm(2.0)
WIDTH = 21 - 4.4  # 본문 폭(cm)


def set_font(run, size=None, bold=None, color=None):
    run.font.name = FONT
    run._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), FONT)
    if size: run.font.size = Pt(size)
    if bold is not None: run.font.bold = bold
    if color is not None: run.font.color.rgb = color


st = doc.styles["Normal"]
st.font.name, st.font.size = FONT, Pt(10.5)
st.element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), FONT)
st.paragraph_format.line_spacing = 1.45
st.paragraph_format.space_after = Pt(6)


def rich(p, text, size=None, color=None, base_bold=False):
    """**굵게** 표시를 처리해 문단에 글자를 넣는다."""
    for i, part in enumerate(re.split(r"\*\*(.+?)\*\*", text)):
        if part:
            set_font(p.add_run(part), size, base_bold or i % 2 == 1, color)
    return p


def para(text, size=None, color=None, after=6, before=0, bold=False, align=None):
    p = doc.add_paragraph()
    p.paragraph_format.space_after, p.paragraph_format.space_before = Pt(after), Pt(before)
    if align: p.alignment = align
    return rich(p, text, size, color, bold)


def bullets(items):
    for t in items:
        p = doc.add_paragraph(style="List Bullet")
        p.paragraph_format.space_after = Pt(3)
        rich(p, t)


def section_title(num, label, title):
    p = doc.add_paragraph()
    p.paragraph_format.space_before, p.paragraph_format.space_after = Pt(18), Pt(2)
    p.paragraph_format.keep_with_next = True
    set_font(p.add_run(f"{num}  {label}"), 9, True, ACCENT)
    h = doc.add_paragraph()
    h.paragraph_format.space_after = Pt(8)
    h.paragraph_format.keep_with_next = True
    set_font(h.add_run(title), 15, True, INK)
    bottom_border(h, LINE)


def sub_title(text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before, p.paragraph_format.space_after = Pt(10), Pt(4)
    p.paragraph_format.keep_with_next = True
    set_font(p.add_run(text), 11.5, True, INK)


def finding(text):
    """한 문장 결론: 왼쪽 강조선이 있는 문단."""
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(8)
    p.paragraph_format.left_indent = Cm(0.35)
    p.paragraph_format.keep_with_next = True
    pPr = p._p.get_or_add_pPr()
    bdr = OxmlElement("w:pBdr")
    left = OxmlElement("w:left")
    for k, v in {"w:val": "single", "w:sz": "18", "w:space": "8", "w:color": "0B6E64"}.items():
        left.set(qn(k), v)
    bdr.append(left)
    pPr.append(bdr)
    rich(p, text, 11, INK, True)


def bottom_border(p, color):
    pPr = p._p.get_or_add_pPr()
    bdr = OxmlElement("w:pBdr")
    b = OxmlElement("w:bottom")
    for k, v in {"w:val": "single", "w:sz": "6", "w:space": "4", "w:color": color}.items():
        b.set(qn(k), v)
    bdr.append(b)
    pPr.append(bdr)


def shade(cell, color):
    tcPr = cell._tc.get_or_add_tcPr()
    s = OxmlElement("w:shd")
    s.set(qn("w:val"), "clear"); s.set(qn("w:color"), "auto"); s.set(qn("w:fill"), color)
    tcPr.append(s)


def table_borders(tbl):
    tblPr = tbl._tbl.tblPr
    b = OxmlElement("w:tblBorders")
    for edge in ["top", "bottom", "insideH", "left", "right", "insideV"]:
        e = OxmlElement(f"w:{edge}")
        if edge in ("left", "right", "insideV"):
            e.set(qn("w:val"), "nil")
        else:
            e.set(qn("w:val"), "single"); e.set(qn("w:sz"), "4"); e.set(qn("w:color"), LINE)
        b.append(e)
    tblPr.append(b)


def table(header, rows, widths, mono_cols=(), bold_first=True, size=9.5):
    if doc.paragraphs:
        doc.paragraphs[-1].paragraph_format.keep_with_next = True
    t = doc.add_table(rows=1, cols=len(header))
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    table_borders(t)
    for i, h in enumerate(header):
        c = t.rows[0].cells[i]
        shade(c, SHADE)
        p = c.paragraphs[0]; p.paragraph_format.space_after = Pt(0)
        set_font(p.add_run(h), 8.5, True, MUTED)
    trPr = t.rows[0]._tr.get_or_add_trPr()
    th = OxmlElement("w:tblHeader"); th.set(qn("w:val"), "true"); trPr.append(th)
    for r in rows:
        cells = t.add_row().cells
        for i, v in enumerate(r):
            p = cells[i].paragraphs[0]; p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.line_spacing = 1.3
            rich(p, v, size, INK, bold_first and i == 0)
    for row in t.rows:
        cs = OxmlElement("w:cantSplit"); cs.set(qn("w:val"), "true"); row._tr.get_or_add_trPr().append(cs)
        for i, w in enumerate(widths):
            row.cells[i].width = Cm(w)
            mar = OxmlElement("w:tcMar")
            for side, v in [("top", 70), ("bottom", 70), ("left", 90), ("right", 90)]:
                m = OxmlElement(f"w:{side}"); m.set(qn("w:w"), str(v)); m.set(qn("w:type"), "dxa"); mar.append(m)
            row.cells[i]._tc.get_or_add_tcPr().append(mar)
    for row in t.rows[:-1]:
        for c in row.cells:
            for p in c.paragraphs:
                p.paragraph_format.keep_with_next = True
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return t


def figure(name, caption, width=WIDTH):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before, p.paragraph_format.space_after = Pt(6), Pt(2)
    p.paragraph_format.keep_with_next = True
    p.add_run().add_picture(str(FIG / f"{name}.png"), width=Cm(width))
    para(caption, 8.5, MUTED, after=10, align=WD_ALIGN_PARAGRAPH.CENTER)


# ---------------- 표지 ----------------
para("PERSONAL PROJECT · DATA ANALYSIS · 2026", 9, ACCENT, after=4, bold=True)
para("선행지표 기반 화장품 성분 트렌드 예측", 22, INK, after=6, bold=True)
para("PDRN이 뜨기 전에 무엇이 먼저 움직였는지 논문·특허·검색·시술 데이터로 추적하고, "
     "같은 신호로 다음 성분과 원료 사업 진입 전략을 찾은 8주 프로젝트입니다.", 11.5, MUTED, after=12)
table(["기간", "역할", "데이터", "도구"],
      [["8주 · 2026년 11월", "기획 · 수집 · 분석 · 시각화 (1인)", "PubMed · KIPRIS · 네이버 데이터랩",
        "Python · pandas · statsmodels · Streamlit"]],
      [3.4, 4.4, 4.4, 4.4], bold_first=False, size=9.5)
para("작성: 주혜우 · 데이터 기준 2026년 10월 · 코드: github.com/jueb9999/cosmetic-ingredient-trend", 9, MUTED, after=10)

sub_title("핵심 결과")
table(["29 성분", "4 / 4", "0.10", "NAD·NMN"],
      [["2010~2026년 월별 논문·특허·검색·시술 데이터",
        "시술 검색이 화장품 검색보다 1~3년 먼저 오른 성분",
        "점수의 과거 예측력(순위상관). 기준 0.44에 못 미침을 직접 검증",
        "논문·특허·검색·시술이 모두 오르는 PDRN 다음 후보"]],
      [4.15] * 4, bold_first=False, size=9)
# 핵심 결과 표의 머리글은 크게
kt = doc.tables[-1]
for c in kt.rows[0].cells:
    for r in c.paragraphs[0].runs:
        r.font.size, r.font.color.rgb = Pt(15), ACCENT

# ---------------- 01 ----------------
section_title("01", "배경과 질문", "원료사는 성분이 뜨기 1~2년 전에 준비해야 합니다")
para("PDRN은 2023~2025년 한국 화장품 시장에서 가장 크게 성장한 성분 중 하나입니다. 원료 회사가 이런 기회를 잡으려면 "
     "소비자 관심이 터지기 전에 원료를 확보하고 제형을 준비해야 합니다. 그래서 세 가지 가설을 세우고 데이터로 확인했습니다.")
table(["가설", "내용", "결과"], [
    ["H1", "논문·특허가 소비자 검색보다 일정한 시차로 먼저 오른다", "일부만 맞음"],
    ["H2", "논문·특허는 오르는데 검색은 아직 낮은 성분이 다음에 뜬다", "과거 데이터에서 맞지 않음"],
    ["업계 가설", "\"피부과 시술이 뜨면 원료 회사가, 그다음 브랜드가 움직인다\" (로레알 인터뷰)", "시술이 먼저인 것은 맞음"],
], [2.4, 9.6, 4.6])

# ---------------- 02 ----------------
section_title("02", "진행 과정", "8주 동안 수집부터 사업 제안까지")
table(["기간", "단계", "한 일"], [
    ["1–2주", "수집과 검색식 다듬기", "네이버·PubMed 수집, 논문 표본을 직접 판정해 검색식 3차 수정"],
    ["3주", "특허 수집과 통합", "KIPRIS 화장품 IPC 필터 점검, 세 데이터를 한 표로 합침"],
    ["4주", "시차 분석", "상승 시작점·교차상관·그랜저 검정, 시술 경로 가설 검증"],
    ["5주", "점수화와 백테스트", "과거 시점마다 점수를 매겨 3년 뒤 결과와 비교"],
    ["6주", "원료 사업 진입 평가", "특허 경쟁 구도와 규제·수급·기술 장벽을 함께 평가"],
    ["7주", "새 후보 탐색", "업계에서 거론되는 9개 성분을 PDRN 직전 모습과 비교"],
    ["8주", "새 후보 심층 분석", "NAD·아젤라산·ECM의 논문·특허 추가 수집, 보고서·대시보드 정리"],
], [2.0, 4.4, 10.2])

# ---------------- 03 ----------------
section_title("03", "데이터와 품질 관리", "숫자를 믿을 수 있게 만드는 데 시간을 썼습니다")
table(["단계", "출처 · 지표", "품질 관리"], [
    ["연구", "PubMed 월별 논문 수", "성분별 무작위 20편을 직접 판정. 정확도 0.5 미만이던 7개 중 6개를 0.85 이상으로 개선"],
    ["특허", "KIPRIS 월별 화장품 특허 출원 수", "화장품 IPC(A61K 8/, A61Q) 필터를 표본으로 점검, 21개 중 16개 정확도 0.8 이상"],
    ["소비자", "네이버 데이터랩 검색 지수", "요청마다 기준이 달라지는 지수를 히알루론산 = 100 공통 기준으로 보정"],
    ["시술", "시술 이름 검색 지수 (리쥬란, 쥬베룩, 리투오 등)", "같은 기준으로 보정"],
    ["기업", "KIPRIS 출원인", "상위 92개 기업을 원료사·ODM·브랜드사·시술 제품사로 직접 분류"],
], [2.0, 5.2, 9.4])

# ---------------- 04 ----------------
section_title("04", "발견 1", "성분이 뜨는 길은 두 가지였습니다")
finding("나이아신아마이드·레티놀은 특허가 2~7년 먼저 움직였지만, PDRN은 반대로 소비자 검색이 먼저였습니다. "
        "그 출발점은 피부과 시술이었습니다.")
table(["성분", "시술 검색", "화장품 검색", "원료사 특허", "브랜드사 특허"], [
    ["PDRN (리쥬란)", "2022-01", "2023-05", "2023-08", "2023-11"],
    ["엑소좀", "2020-12", "2022-11", "2021-12", "2020-11"],
    ["스피큘 (MTS)", "2018-03", "2019-06", "2023-07", "–"],
    ["글루타치온", "2017-04", "2020-03", "–", "–"],
], [4.0, 3.15, 3.15, 3.15, 3.15])
para("각 단계에서 2016년 이후 늘어난 양이 누적 25%에 도달한 달(T25). 모든 단계를 같은 기간, 같은 기준으로 비교했습니다.", 8.5, MUTED)
figure("w4_procedure_path", "실선 = 검색량, 점선 = 출원인 유형별 특허 (단계별 최댓값 = 1). 나이아신아마이드는 시술이 없는 비교군입니다.")
table(["경로", "순서", "대표 성분 · 먼저 볼 신호"], [
    ["기업·연구 주도", "특허 → (2~6년) → 소비자 검색", "나이아신아마이드, 레티놀 · **특허**"],
    ["시술 주도", "시술 검색 → (1~3년) → 화장품 검색 → 원료사·브랜드 특허", "PDRN, 엑소좀, 스피큘, 글루타치온 · **시술 검색량**"],
], [3.2, 7.2, 6.2])
para("업계 가설 중 \"시술이 먼저\"는 4개 성분 모두에서 확인됐습니다. 반면 \"원료사 → 브랜드\" 순서는 몇 달 차이로 약하게만 보였습니다. "
     "원료사는 특허 없이 신원료를 내는 경우가 많아 특허만으로는 움직임을 다 보기 어렵습니다.")

# ---------------- 05 ----------------
section_title("05", "발견 2", "점수 하나로 다음 성분을 맞히기는 어려웠습니다")
finding("\"논문·특허는 오르는데 검색은 아직 낮은 성분\" 점수를 과거 12개 시점에서 매겨 보니, "
        "3년 뒤 결과와의 순위상관이 평균 0.10이었습니다.")
table(["방법", "순위상관 평균", "상위 5개 중 3년 뒤 검색 2배 이상"], [
    ["H2 점수", "0.10", "30%"],
    ["논문·특허 신호만", "0.01", "37%"],
    ["단순 추세 (지금 오르는 검색이 계속 오름)", "0.19", "42%"],
    ["무작위로 고를 때", "0", "26%"],
], [8.6, 3.4, 4.6])
figure("w5_scores", "왼쪽: 2026년 10월 기준 점수 구성. 오른쪽: 기준 시점별 순위상관. 회색 띠는 통계적으로 의미 없는 범위(|순위상관| < 0.44)입니다.")
bullets(["성분마다 먼저 움직이는 신호와 시차가 달라서, 하나의 점수로 묶으면 신호가 섞여 사라졌습니다.",
         "그래서 점수는 예측이 아니라 **살펴볼 후보를 좁히는 거름망**으로만 쓰기로 했습니다."])

# ---------------- 06 ----------------
section_title("06", "발견 3", "원료 사업 관점에서 본 후보 성분")
finding("시장 매력도와 진입 용이성(특허 경쟁 구도, 규제, 원료 수급, 기술 장벽)으로 평가하자 "
        "식물성 PDRN은 빈 시장이 아니라 기존 원료사들이 옮겨 가는 시장으로 드러났습니다.")
figure("w6_feasibility", "원 크기 = 2021-01~2025-04 화장품 특허 수. 정성 항목은 공개 자료를 근거로 1~3점을 매기고 출처를 남겼습니다.", width=11)
table(["성분", "판정", "근거"], [
    ["쌀", "우선 검토", "규제·수급·기술 부담이 낮음. 대신 진입 장벽이 낮아 차별화가 어려움"],
    ["식물성 PDRN", "우선 검토", "PDRN 화장품 특허의 42%가 식물 유래, 출원 상위 기업이 기존 PDRN 원료사와 같음"],
    ["마이크로바이옴", "경계", "대기업 6곳 참여"],
    ["재조합 콜라겐", "경계", "특허의 67%가 해외 기업, 기술 장벽 높음"],
    ["스피큘", "진입 어려움", "원료 해외 의존, 이미 제품이 많고 검색은 정점의 약 35%"],
    ["아스타잔틴", "보류", "검색 감소, 시장 84%가 저가 합성품"],
], [3.4, 2.8, 10.4])

# ---------------- 07 ----------------
section_title("07", "발견 4", "PDRN 다음 후보: NAD·NMN, 아젤라산, ECM")
finding("처음 고른 20개 중 15개는 이미 유행이 지난 성분이었습니다. "
        "업계에서 거론되는 새 성분 9개를 PDRN이 뜨기 직전 모습과 비교했습니다.")
figure("w7_next_candidates", "왼쪽: 지금 각 성분의 위치와 PDRN이 지나온 길(매년 10월). 오른쪽: 스킨부스터 시술 검색량. "
       "리쥬란·쥬베룩은 2025년 정점 뒤 감소, 리투오(ECM)만 상승 중입니다.")
figure("w8_new_candidates_upstream", "새 후보의 연간 논문·화장품 특허 수. 점선은 아직 덜 모인 해입니다.")
table(["성분", "검색", "논문", "화장품 특허", "판단"], [
    ["NAD·NMN", "1년 +541%", "46 → 95+편", "2~4 → 7~10건",
     "논문·특허·검색·시술이 모두 오르는 유일한 성분. 2026년 6월 급등 후 조정 중이라 지속성 확인 필요"],
    ["아젤라산", "1년 +167%", "연 20~38편", "연 0~8건",
     "검색 모양이 PDRN 직전과 가장 비슷. 검색 대부분이 처방약이라 화장품 수요 분리 필요"],
    ["ECM", "아직 작음", "78 → 230+편", "연 0~5건",
     "시술(리투오)과 연구가 앞서는 초기 단계. 인체조직 원료라 규제 부담"],
], [2.4, 2.4, 2.6, 2.6, 6.6])
para("**시술이 뜬다고 화장품이 다 따라오지는 않았습니다.** 쥬베룩은 리쥬란만큼 큰 시술이 됐지만 PDLLA 화장품 검색은 "
     "PDRN 때의 10분의 1 수준입니다. 바르는 형태로 설명하기 어려운 성분은 화장품으로 잘 넘어가지 않는 것으로 보입니다.")

# ---------------- 08 ----------------
section_title("08", "제안", "원료 사업 전략 제안")
table(["대상", "제안"], [
    ["모니터링", "기업·연구 주도 성분은 특허, 시술 주도 성분은 시술 검색량을 따로 추적. 시술 신호는 화장품보다 1~3년 앞섬"],
    ["NAD·NMN", "원료 소싱과 안정화 기술(빛·열에 약함)을 먼저 검토하고, 2027년 상반기까지 검색 회복을 확인한 뒤 투자 결정"],
    ["ECM", "인체조직 대신 식물·미생물 유래 ECM 유사 소재로 '바르는 ECM'을 기획하고 리투오 추이를 분기마다 확인"],
    ["아젤라산", "화장품 배합 한도를 식약처 고시로 확인한 뒤 저자극 제형(입자·캡슐화) 원료로 차별화"],
    ["식물성 PDRN", "순도·분자량 시험 성적서와 사람 대상 효능 자료로 차별화할 수 있을 때만 진입"],
], [3.2, 13.4])

# ---------------- 09 ----------------
section_title("09", "문제 해결 기록", "분석하며 부딪힌 문제와 해결")
table(["문제", "해결"], [
    ["네이버 검색 지수는 요청마다 기준이 달라 성분끼리 비교가 안 됨",
     "모든 요청에 히알루론산을 함께 넣고, 그 평균이 100이 되도록 다시 맞춰 하나의 기준으로 통일"],
    ["논문 검색식에 화장품과 무관한 논문이 섞임",
     "성분별 무작위 20편을 직접 O/X 판정하고 검색식을 최대 3차까지 수정. 정확도 0.5 미만이던 7개 중 6개를 0.85 이상으로 개선"],
    ["특허는 출원 후 18개월 뒤 공개되어 최근 값이 실제보다 작음",
     "최근 18개월을 분석에서 빼고, 과거 시점을 재현할 때도 그 시점에 볼 수 있던 특허만 사용"],
    ["지표마다 다른 잣대로 시점을 재고 있었음",
     "모든 단계를 같은 기간, 같은 기준(늘어난 양의 누적 25%·50% 도달 시점)으로 다시 계산"],
    ["점수가 이미 유행이 지난 성분을 상위에 올림",
     "원인을 찾아 '정점 대비 70% 미만이면 유행 지남' 판정을 추가하고, 후보 목록을 넓혀 새 성분 9개를 조사"],
], [6.2, 10.4])

# ---------------- 10 ----------------
section_title("10", "한계와 다음 단계", "한계와 다음 단계")
bullets(["**검색량은 관심이지 매출이 아닙니다.** 약 검색이 섞이거나 성분 이름이 다른 뜻으로 쓰일 수 있습니다.",
         "**생존 편향이 있습니다.** 성분을 2026년 기준으로 골라 백테스트에 결국 뜬 성분이 많이 포함됐습니다.",
         "**사례가 적습니다.** 시차 결론은 4개 성분, 'PDRN 직전' 기준은 PDRN 한 사례에서 나왔습니다.",
         "**정성 평가에는 판단이 들어갑니다.** 실제 사업 판단에는 원료 견적, 식약처 고시 원문, 업계 인터뷰가 필요합니다."])
para("**다음 단계:** 새 후보의 검색·시술 추이를 분기마다 갱신하고, 검색어 순위에서 떠오르는 성분을 자동으로 찾아 생존 편향을 줄이며, "
     "판매 순위 데이터로 검색 신호가 매출로 이어지는지 확인합니다.", before=4)

# 쪽 번호 (바닥글 가운데)
fp = sec.footer.paragraphs[0]
fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = fp.add_run()
for tag, text in [("begin", None), (None, "PAGE"), ("end", None)]:
    if tag:
        f = OxmlElement("w:fldChar"); f.set(qn("w:fldCharType"), tag); run._r.append(f)
    else:
        it = OxmlElement("w:instrText"); it.set(qn("xml:space"), "preserve"); it.text = text; run._r.append(it)
set_font(run, 8.5, False, MUTED)

doc.core_properties.title = "선행지표 기반 화장품 성분 트렌드 예측"
doc.core_properties.author = "주혜우"
OUT.parent.mkdir(exist_ok=True)
doc.save(OUT)
print("저장:", OUT)
