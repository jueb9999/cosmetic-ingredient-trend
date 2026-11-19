"""네이버 데이터랩 검색어 트렌드 수집기.

하는 일
1. config/keywords.csv에서 성분별 검색어 묶음을 읽는다.
2. 네이버 API는 한 번에 키워드 그룹을 5개까지만 받으므로
   [앵커 1개 + 성분 4개]씩 나눠서 요청한다.
3. 응답 값(ratio)은 '그 요청 안에서 가장 높은 값 = 100'인 상대값이라
   요청끼리 비교가 안 된다. 그래서 모든 요청에 같은 앵커(히알루론산)를 넣고,
   앵커 평균이 100이 되도록 다시 맞춘다(value_scaled).
4. 원본 응답(JSON)과 정리된 표(CSV)를 data/raw/에 날짜를 붙여 저장한다.

실행 예
    python src/collect_naver.py --dry-run          # 요청 계획만 출력 (API 키 없어도 됨)
    python src/collect_naver.py                    # 실제 수집
    python src/collect_naver.py --start 2016-01-01 --end 2026-10-31
"""
import argparse
import json
import os
import sys
import time

import pandas as pd
import requests
from dotenv import load_dotenv

from common import load_keywords, raw_path, ROOT

API_URL = "https://naverapihub.apigw.ntruss.com/search-trend/v1/search"
MAX_GROUPS_PER_REQUEST = 5  # 네이버 API 제한
SLEEP_SEC = 0.5  # 요청 사이 쉬는 시간 (서버 배려 + 한도 보호)


def chunk(items, size):
    """리스트를 size개씩 자른다. 예: chunk([1..9], 4) -> [1-4], [5-8], [9]"""
    return [items[i:i + size] for i in range(0, len(items), size)]


def build_requests(kw, start, end):
    """API에 보낼 요청 본문(body) 목록을 만든다."""
    anchor = kw[kw["group"] == "anchor"].iloc[0]
    targets = kw[kw["group"] != "anchor"]

    anchor_group = {"groupName": anchor["ingredient_id"],
                    "keywords": anchor["naver_keywords"]}

    bodies = []
    for part in chunk(list(targets.itertuples()), MAX_GROUPS_PER_REQUEST - 1):
        groups = [anchor_group] + [
            {"groupName": r.ingredient_id, "keywords": r.naver_keywords}
            for r in part
        ]
        bodies.append({
            "startDate": start,
            "endDate": end,
            "timeUnit": "month",
            "keywordGroups": groups,
        })
    return bodies, anchor["ingredient_id"]


def call_api(body, client_id, client_secret):
    headers = {
        "X-NCP-APIGW-API-KEY-ID": client_id,
        "X-NCP-APIGW-API-KEY": client_secret,
        "Content-Type": "application/json",
    }
    resp = requests.post(API_URL, headers=headers,
                         data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                         timeout=30)
    if resp.status_code != 200:
        # 401: 키가 틀림 / 403: 데이터랩 API 사용 설정 안 함 / 429: 한도 초과
        raise RuntimeError(f"네이버 API 오류 {resp.status_code}: {resp.text}")
    return resp.json()


def to_long(response, request_no, anchor_id):
    """API 응답 하나를 '성분 x 월' 형태의 긴 표로 바꾸고 앵커 기준으로 다시 맞춘다."""
    rows = []
    for result in response["results"]:
        for point in result["data"]:
            rows.append({
                "ingredient_id": result["title"],
                "month": point["period"][:7],  # 2020-01-01 -> 2020-01
                "ratio": point["ratio"],
                "request_no": request_no,
            })
    df = pd.DataFrame(rows)

    # 검색량이 너무 적은 달은 응답에서 빠지므로 0으로 채운다
    months = pd.period_range(response["startDate"][:7], response["endDate"][:7], freq="M").astype(str)
    titles = [r["title"] for r in response["results"]]
    full = pd.MultiIndex.from_product([titles, months], names=["ingredient_id", "month"])
    df = (df.set_index(["ingredient_id", "month"])["ratio"]
            .reindex(full, fill_value=0.0).reset_index())
    df["request_no"] = request_no

    # 앵커 평균이 100이 되도록 같은 배율을 곱한다 -> 요청끼리 비교 가능
    anchor_mean = df.loc[df["ingredient_id"] == anchor_id, "ratio"].mean()
    if anchor_mean == 0:
        raise RuntimeError("앵커 검색량이 0입니다. 앵커 키워드를 바꿔 주세요.")
    df["value_scaled"] = df["ratio"] * (100 / anchor_mean)
    return df


def main():
    parser = argparse.ArgumentParser(description="네이버 데이터랩 검색어 트렌드 수집")
    parser.add_argument("--start", default="2016-01-01", help="시작일 (2016-01-01 이후)")
    parser.add_argument("--end", default=pd.Timestamp.today().strftime("%Y-%m-%d"), help="종료일")
    parser.add_argument("--dry-run", action="store_true", help="요청 계획만 출력")
    args = parser.parse_args()

    kw = load_keywords()
    bodies, anchor_id = build_requests(kw, args.start, args.end)
    print(f"성분 {len(kw) - 1}개 + 앵커({anchor_id}) -> 요청 {len(bodies)}번")

    if args.dry_run:
        for i, b in enumerate(bodies, 1):
            names = [g["groupName"] for g in b["keywordGroups"]]
            print(f"  요청 {i}: {names}")
        return

    load_dotenv(ROOT / ".env")
    client_id = os.getenv("NAVER_CLIENT_ID")
    client_secret = os.getenv("NAVER_CLIENT_SECRET")
    if not client_id or not client_secret:
        sys.exit(".env 파일에 NAVER_CLIENT_ID, NAVER_CLIENT_SECRET을 넣어 주세요. (.env.example 참고)")

    raw_responses, frames = [], []
    for i, body in enumerate(bodies, 1):
        print(f"요청 {i}/{len(bodies)} ...", end=" ")
        resp = call_api(body, client_id, client_secret)
        raw_responses.append(resp)
        frames.append(to_long(resp, i, anchor_id))
        print("완료")
        time.sleep(SLEEP_SEC)

    # 1) 원본 응답 저장 (나중에 가공 방식을 바꿔도 다시 호출할 필요 없음)
    json_path = raw_path("naver_raw", "json")
    json_path.write_text(json.dumps(raw_responses, ensure_ascii=False, indent=2), encoding="utf-8")

    # 2) 정리된 표 저장. 앵커는 요청마다 같은 값이 들어 있으니 한 번만 남긴다
    out = pd.concat(frames, ignore_index=True)
    out = out.drop_duplicates(subset=["ingredient_id", "month"], keep="first")
    out.insert(1, "stage", "consumer")
    out.insert(2, "source", "naver")
    csv_path = raw_path("naver")
    out.to_csv(csv_path, index=False, encoding="utf-8-sig")

    print(f"\n저장 완료\n  원본: {json_path}\n  표:   {csv_path}  ({len(out):,}행)")
    print("\n성분별 최근 12개월 평균 (앵커=100 기준):")
    recent = out.sort_values("month").groupby("ingredient_id").tail(12)
    print(recent.groupby("ingredient_id")["value_scaled"].mean().sort_values(ascending=False).round(1).to_string())


if __name__ == "__main__":
    main()
