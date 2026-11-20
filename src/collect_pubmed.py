"""PubMed 월별 논문 수 수집기.

하는 일
1. config/keywords.csv의 pubmed_query(검색식)를 읽는다.
2. NCBI E-utilities의 esearch API로 '그 달에 PubMed에 등록된 논문 수'만 센다.
   (출판일 기준으로 세면 온라인 선공개일과 정식 출판일이 다른 논문이 두 달에 걸쳐
    두 번 세어진다. 등록일(edat)은 논문마다 하나뿐이라 한 번만 세어진다)
   (논문 내용은 받지 않고 개수만 받아서 빠르고 가볍다)
3. 성분 x 월 표를 data/raw/pubmed_<날짜>.csv로 저장한다.
   중간에 끊겨도 처음부터 다시 하지 않도록 진행 상황을 임시 파일에 계속 저장한다.

호출 수 = 성분 수 x 개월 수 (예: 21개 x 120개월 = 2,520번)
  - API 키 없음: 초당 3번 -> 약 15분
  - API 키 있음: 초당 10번 -> 약 5분

실행 예
    python src/collect_pubmed.py --dry-run                 # 검색식과 호출 수만 확인
    python src/collect_pubmed.py --only PDRN --start 2015-01  # 한 성분만 시험 수집
    python src/collect_pubmed.py                           # 전체 수집
"""
import argparse
import calendar
import os
import time

import pandas as pd
import requests
from dotenv import load_dotenv

from common import load_keywords, raw_path, ROOT, RAW_DIR

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
TOOL_NAME = "cosmetic-ingredient-trend"


def month_range(start, end):
    """'2015-01' ~ '2026-10' 사이의 모든 달을 돌려준다."""
    return pd.period_range(start, end, freq="M")


def count_papers(query, period, api_key=None, email=None, retries=3):
    """특정 달(period)에 PubMed에 등록된 논문 수를 센다."""
    last_day = calendar.monthrange(period.year, period.month)[1]
    params = {
        "db": "pubmed",
        "term": query,
        "rettype": "count",
        "retmode": "json",
        "datetype": "edat",  # PubMed 등록일 기준 (논문마다 하나라 중복 없음)
        "mindate": f"{period.year}/{period.month:02d}/01",
        "maxdate": f"{period.year}/{period.month:02d}/{last_day}",
        "tool": TOOL_NAME,
    }
    if api_key:
        params["api_key"] = api_key
    if email:
        params["email"] = email

    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(ESEARCH_URL, params=params, timeout=30)
            if resp.status_code == 429:  # 너무 빨리 호출함 -> 잠깐 쉬고 재시도
                time.sleep(2 * attempt)
                continue
            resp.raise_for_status()
            return int(resp.json()["esearchresult"]["count"])
        except (requests.RequestException, KeyError, ValueError) as e:
            if attempt == retries:
                print(f"\n  ! {period} 실패: {e}")
                return None  # 실패한 달은 비워 두고 나중에 다시 수집
            time.sleep(2 * attempt)


def main():
    parser = argparse.ArgumentParser(description="PubMed 월별 논문 수 수집")
    parser.add_argument("--start", default="2015-01", help="시작 월 (YYYY-MM)")
    parser.add_argument("--end", default=(pd.Timestamp.today() - pd.offsets.MonthEnd(1)).strftime("%Y-%m"),
                        help="종료 월 (기본: 지난달)")
    parser.add_argument("--only", nargs="*", help="특정 성분만 수집 (예: --only PDRN CICA)")
    parser.add_argument("--dry-run", action="store_true", help="검색식과 호출 수만 출력")
    parser.add_argument("--scan", action="store_true",
                        help="7주차 새 후보(config/scan_keywords.csv) -> pubmed_scan_<날짜>.csv (기존 파일을 덮어쓰지 않음)")
    args = parser.parse_args()

    kw = load_keywords()
    name = "pubmed"
    if args.scan:
        kw = pd.read_csv(ROOT / "config" / "scan_keywords.csv", encoding="utf-8-sig", dtype=str, keep_default_na=False)
        kw = kw[kw["pubmed_query"] != ""]
        name = "pubmed_scan"
    if args.only:
        kw = kw[kw["ingredient_id"].isin(args.only)]
    months = month_range(args.start, args.end)
    print(f"성분 {len(kw)}개 x {len(months)}개월 = 호출 {len(kw) * len(months):,}번")

    if args.dry_run:
        for r in kw.itertuples():
            print(f"  {r.ingredient_id:16s} {r.pubmed_query}")
        print("\n검색식이 맞는지는 https://pubmed.ncbi.nlm.nih.gov 검색창에 그대로 붙여넣어 확인하세요.")
        return

    load_dotenv(ROOT / ".env")
    api_key = os.getenv("NCBI_API_KEY") or None
    email = os.getenv("NCBI_EMAIL") or None
    sleep_sec = 0.11 if api_key else 0.34  # 초당 10번 / 3번 제한 지키기
    print("API 키 사용" if api_key else "API 키 없음 (느리게 수집합니다)")

    # 중간 저장 파일: 끊겼다가 다시 실행하면 이미 받은 칸은 건너뛴다
    progress_path = RAW_DIR / f"{name}_progress.csv"
    done = {}
    if progress_path.exists():
        prev = pd.read_csv(progress_path)
        prev = prev.dropna(subset=["value"])
        done = {(r.ingredient_id, r.month): r.value for r in prev.itertuples()}
        print(f"이전 진행분 {len(done):,}칸을 이어서 사용합니다.")

    rows = []
    for r in kw.itertuples():
        print(f"{r.ingredient_id:16s}", end=" ", flush=True)
        for i, p in enumerate(months):
            key = (r.ingredient_id, str(p))
            if key in done:
                value = done[key]
            else:
                value = count_papers(r.pubmed_query, p, api_key, email)
                time.sleep(sleep_sec)
            rows.append({"ingredient_id": r.ingredient_id, "month": str(p), "value": value})
            if i % 12 == 11:
                print(".", end="", flush=True)  # 1년치마다 점 하나
        pd.DataFrame(rows).to_csv(progress_path, index=False)
        total = sum(x["value"] or 0 for x in rows if x["ingredient_id"] == r.ingredient_id)
        print(f" 총 {total:,}편")

    out = pd.DataFrame(rows)
    out.insert(1, "stage", "science")
    out.insert(2, "source", "pubmed")
    out["value_type"] = "count"
    csv_path = raw_path(name)
    out.to_csv(csv_path, index=False, encoding="utf-8-sig")

    failed = out["value"].isna().sum()
    print(f"\n저장 완료: {csv_path}  ({len(out):,}행, 실패 {failed}칸)")
    if failed:
        print("실패한 칸이 있으면 같은 명령을 한 번 더 실행하세요. 받은 칸은 건너뛰고 빈 칸만 다시 받습니다.")
    else:
        progress_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
