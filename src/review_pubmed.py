"""PubMed 검색식 정확도 점검 도구 (2주차).

왜 필요한가
  collect_pubmed.py는 검색식에 걸린 논문 '개수'만 센다. 그런데 검색식에 화장품과
  상관없는 논문(예: 쌀 -> 가축 사료, 비소)이 많이 섞이면 개수가 부풀려지고,
  "논문이 먼저 늘었다"는 분석 결론이 틀어질 수 있다.
  그래서 성분마다 논문 몇 편을 직접 읽어 보고 '관련 있는 논문 비율(정확도)'을 잰다.

왜 무작위로 뽑는가
  관련도 상위 20편은 검색어와 가장 잘 맞는 논문이라 정확도가 실제보다 높게 나온다.
  검색 결과 전체에서 무작위로 뽑아야 전체 논문 중 몇 %가 진짜 관련 논문인지 추정할 수 있다.
  seed(난수 시작값)를 고정해서 다시 실행해도 같은 논문이 뽑힌다.

사용 순서
  1) 점검 파일 만들기
       python src/review_pubmed.py                      # 전체 성분, 성분당 20편
       python src/review_pubmed.py --only RICE FUCOXANTHIN
  2) data/review/pubmed_review_<날짜>.csv를 엑셀로 열어 relevant 칸에 O 또는 X를 적고 저장
       O = 화장품·피부에 바르는 용도와 관련 있음 / X = 관련 없음 / 애매하면 ? (계산에서 빠짐)
  3) 정확도 계산
       python src/review_pubmed.py --summary data/review/pubmed_review_<날짜>.csv
"""
import argparse
import os
import random
import time

import pandas as pd
import requests
from dotenv import load_dotenv

from common import load_keywords, today_tag, ROOT

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
ESUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
TOOL_NAME = "cosmetic-ingredient-trend"
REVIEW_DIR = ROOT / "data" / "review"
MAX_IDS = 9999  # esearch가 한 번에 돌려주는 최대 논문 번호 수


def get(url, params, retries=3):
    """NCBI API를 호출한다. 실패하면 잠깐 쉬고 다시 시도한다."""
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, params=params, timeout=60)
            if resp.status_code == 429:  # 너무 빨리 호출함
                time.sleep(2 * attempt)
                continue
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError):
            if attempt == retries:
                raise
            time.sleep(2 * attempt)


def search_ids(query, start, end, base):
    """기간 안에 PubMed에 등록된 논문의 번호(PMID) 목록과 전체 개수를 돌려준다."""
    params = {**base, "db": "pubmed", "term": query, "retmode": "json", "retmax": MAX_IDS,
              "datetype": "edat", "mindate": start, "maxdate": end}
    result = get(ESEARCH_URL, params)["esearchresult"]
    return result["idlist"], int(result["count"])


def summaries(pmids, base):
    """PMID 목록의 제목·학술지·출판연도를 받아온다."""
    params = {**base, "db": "pubmed", "id": ",".join(pmids), "retmode": "json"}
    result = get(ESUMMARY_URL, params)["result"]
    out = {}
    for pmid in pmids:
        doc = result.get(pmid, {})
        out[pmid] = {
            "year": (doc.get("pubdate") or "")[:4],
            "journal": doc.get("fulljournalname") or doc.get("source", ""),
            "title": doc.get("title", ""),
        }
    return out


def make_review(args):
    kw = load_keywords()
    if args.only:
        kw = kw[kw["ingredient_id"].isin(args.only)]

    load_dotenv(ROOT / ".env")
    base = {"tool": TOOL_NAME}
    if os.getenv("NCBI_API_KEY"):
        base["api_key"] = os.getenv("NCBI_API_KEY")
    if os.getenv("NCBI_EMAIL"):
        base["email"] = os.getenv("NCBI_EMAIL")
    sleep_sec = 0.11 if "api_key" in base else 0.34

    rows = []
    for r in kw.itertuples():
        ids, total = search_ids(r.pubmed_query, args.start, args.end, base)
        time.sleep(sleep_sec)
        rng = random.Random(f"{args.seed}-{r.ingredient_id}")  # 성분마다 고정된 무작위 뽑기
        picked = rng.sample(ids, min(args.n, len(ids)))
        info = summaries(picked, base) if picked else {}
        time.sleep(sleep_sec)
        note = "" if total <= MAX_IDS else f" (전체 중 앞 {MAX_IDS:,}편에서 뽑음)"
        print(f"{r.ingredient_id:16s} 전체 {total:>6,}편 중 {len(picked)}편 뽑음{note}")
        for i, pmid in enumerate(picked, 1):
            rows.append({
                "ingredient_id": r.ingredient_id,
                "name_ko": r.name_ko,
                "no": i,
                "relevant": "",  # 여기에 O / X / ? 를 적는다
                "memo": "",
                "title": info[pmid]["title"],
                "journal": info[pmid]["journal"],
                "year": info[pmid]["year"],
                "pmid": pmid,
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "total_papers": total,
                "query": r.pubmed_query,
            })

    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    path = REVIEW_DIR / f"pubmed_review_{today_tag()}.csv"
    n = 2
    while path.exists():  # 이미 O/X를 적은 파일을 덮어쓰지 않도록 번호를 붙인다
        path = REVIEW_DIR / f"pubmed_review_{today_tag()}_{n}.csv"
        n += 1
    pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8-sig")  # 엑셀에서 한글 안 깨지게
    print(f"\n저장 완료: {path}")
    print("엑셀로 열어 relevant 칸에 O / X / ? 를 적고 저장한 뒤, --summary 로 정확도를 계산하세요.")


def read_marked(path):
    """사람이 표시한 점검 파일을 읽는다. 엑셀이 다른 인코딩으로 저장해도 읽히게 한다."""
    for enc in ("utf-8-sig", "cp949"):
        try:
            return pd.read_csv(path, encoding=enc, dtype={"pmid": str})
        except UnicodeDecodeError:
            continue
    raise ValueError("파일 인코딩을 읽지 못했습니다. 엑셀에서 'CSV UTF-8'로 저장해 주세요.")


def summarize(path):
    df = read_marked(path)
    mark = df["relevant"].fillna("").astype(str).str.strip().str.upper()
    mark = mark.replace({"0": "O", "Ｏ": "O", "Ｘ": "X", "○": "O", "×": "X"})
    df["mark"] = mark

    out = []
    for ing, g in df.groupby("ingredient_id", sort=False):
        o, x = (g["mark"] == "O").sum(), (g["mark"] == "X").sum()
        unsure, blank = (g["mark"] == "?").sum(), (g["mark"] == "").sum()
        judged = o + x
        out.append({
            "ingredient_id": ing,
            "checked": judged,
            "relevant_O": o,
            "irrelevant_X": x,
            "unsure": unsure,
            "blank": blank,
            "precision": round(o / judged, 2) if judged else None,
            "total_papers": g["total_papers"].iloc[0],
        })
    res = pd.DataFrame(out)

    def verdict(p):
        if pd.isna(p):
            return "미검토"
        if p >= 0.8:
            return "양호"
        if p >= 0.5:
            return "다듬기 권장"
        return "다듬기 필요"

    res["verdict"] = res["precision"].map(verdict)
    out_path = path.parent / path.name.replace("pubmed_review_", "pubmed_precision_")
    res.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(res.to_string(index=False))
    print(f"\n저장 완료: {out_path}")
    print("기준: 정확도 0.8 이상 양호 / 0.5~0.8 다듬기 권장 / 0.5 미만 다듬기 필요")


def main():
    parser = argparse.ArgumentParser(description="PubMed 검색식 정확도 점검")
    parser.add_argument("--only", nargs="*", help="특정 성분만 (예: --only RICE FUCOXANTHIN)")
    parser.add_argument("--n", type=int, default=20, help="성분당 뽑을 논문 수 (기본 20)")
    parser.add_argument("--start", default="2015/01/01", help="기간 시작 (수집 기간과 같게)")
    parser.add_argument("--end", default=pd.Timestamp.today().strftime("%Y/%m/%d"), help="기간 끝")
    parser.add_argument("--seed", type=int, default=2026, help="무작위 시작값 (같으면 같은 논문이 뽑힘)")
    parser.add_argument("--summary", help="O/X를 표시한 점검 파일 경로 -> 정확도 계산")
    args = parser.parse_args()

    if args.summary:
        from pathlib import Path
        summarize(Path(args.summary))
    else:
        make_review(args)


if __name__ == "__main__":
    main()
