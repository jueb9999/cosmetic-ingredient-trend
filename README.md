# 선행지표 기반 화장품 성분 트렌드 예측

PDRN이 유행하기 전에 어떤 데이터가 먼저 움직였는지 찾고, 같은 신호를 보이는 다음 후보 성분을 찾는 프로젝트입니다.
## 진행 상황

| 주차 | 내용 | 상태 |
|---|---|---|
| 1주차 | 키워드 사전 초안, 네이버 검색량·PubMed 논문 수 수집, 키워드 검수 1회차 | 완료 |
| 2주차 | 검색어 다듬기(검색식 정확도 점검), README 정리 | 진행 중 |
| 3주차 | KIPRIS 특허 수집, 데이터 통합 | 예정 |

## 폴더 구조

```
cosmetic-ingredient-trend/
├── config/keywords.csv      # 성분별 검색어 사전 (엑셀로 열어서 수정 가능)
├── config/keywords_backup.csv  # 검수 전 원본 사전 (비교용)
├── src/
│   ├── common.py            # 공통 함수
│   ├── collect_naver.py     # 네이버 데이터랩 검색량 수집
│   ├── collect_pubmed.py    # PubMed 월별 논문 수 수집
│   ├── review_pubmed.py     # PubMed 검색식 정확도 점검 (무작위 표본 O/X)
│   └── quick_plot.py        # 수집 결과 확인용 그래프
├── data/raw/                # 수집 원본 (파일명에 수집 날짜)
├── data/processed/          # 가공 데이터·그래프
├── data/review/             # 검색식 점검 표본(O/X 표시)과 정확도 결과
├── .env.example             # API 키 입력 양식
└── requirements.txt
```

## 처음 실행하기

### 1. 준비
1. Python 3.10 이상과 VS Code를 설치합니다.
2. 이 폴더를 VS Code로 열고, 터미널(상단 메뉴 Terminal > New Terminal)을 엽니다.
3. 가상환경을 만들고 패키지를 설치합니다.

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Mac
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. API 키 넣기
1. `.env.example`을 복사해서 이름을 `.env`로 바꿉니다.
2. 아래 안내대로 키를 받아 `=` 뒤에 넣습니다. `.env`는 `.gitignore`에 들어 있어 GitHub에 올라가지 않습니다.

| 키 | 필수 | 발급처 |
|---|---|---|
| `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET` | 필수 | 네이버 클라우드 플랫폼(ncloud.com) > NAVER API HUB에서 Application을 만들고 데이터랩 검색어 트렌드 API를 추가한 뒤, 인증 정보의 Client ID / Client Secret을 복사 |
| `NCBI_API_KEY` | 선택 | NCBI 계정 로그인 > Account Settings > API Key Management. 없어도 동작하지만 있으면 PubMed 수집이 약 3배 빠름 |
| `NCBI_EMAIL` | 선택 | 본인 이메일. NCBI가 과도한 호출 시 연락용으로 권장 |

> **네이버 키 주의:** 2026-07-31부터 데이터랩 API 신규 키는 NAVER API HUB에서만 발급됩니다. 이 코드는 HUB 주소(`naverapihub.apigw.ntruss.com`)와 HUB 인증 헤더(`X-NCP-APIGW-API-KEY-ID` / `X-NCP-APIGW-API-KEY`)를 사용하므로, 예전 네이버 개발자센터(developers.naver.com)에서 받은 키로는 동작하지 않습니다.

### 3. 수집 실행

```bash
python src/collect_naver.py --dry-run     # 요청 계획 확인 (키 없어도 됨)
python src/collect_naver.py               # 네이버 수집 (1분 이내)

python src/collect_pubmed.py --dry-run    # 검색식 확인
python src/collect_pubmed.py --only PDRN --start 2024-01   # 시험 수집
python src/collect_pubmed.py              # 전체 수집 (키 없으면 약 15분)

python src/quick_plot.py                  # 그래프로 확인
```

### 4. PubMed 검색식 정확도 점검 (선택)

검색식에 화장품과 상관없는 논문이 섞이면 논문 수가 부풀려집니다. 성분마다 논문을 무작위로 뽑아 사람이 직접 관련 여부를 표시하고 정확도(관련 논문 비율)를 계산합니다.

```bash
python src/review_pubmed.py                       # 성분당 무작위 20편 -> data/review/pubmed_review_<날짜>.csv
# 엑셀로 열어 relevant 칸에 O(관련) / X(무관) / ?(애매) 표시 후 저장
python src/review_pubmed.py --summary data/review/pubmed_review_<날짜>.csv   # 성분별 정확도 계산
```

## 데이터 설명

| 파일 | 컬럼 | 설명 |
|---|---|---|
| `naver_<날짜>.csv` | ratio | 네이버가 준 원래 값 (그 요청 안에서 최댓값 = 100) |
| | value_scaled | 앵커(히알루론산) 평균 = 100으로 다시 맞춘 값. **성분끼리 비교할 때는 이 값을 사용** |
| `naver_raw_<날짜>.json` | | API 원본 응답 (가공 방식을 바꿀 때 재호출 없이 사용) |
| `pubmed_<날짜>.csv` | value | 그 달에 PubMed에 등록된 논문 수 (등록일 기준이라 한 논문은 한 달에만 세어짐) |

## 알아둘 한계
- 네이버 검색량은 절대 검색 수가 아니라 상대지수입니다. 앵커로 맞춰도 앵커보다 훨씬 작은 성분은 소수점 단위 오차가 커집니다.
- 검색량이 너무 적은 달은 네이버가 값을 주지 않아 0으로 채웠습니다.
- PubMed 검색식은 무작위 20편 O/X 점검을 최대 3차까지 거쳐 다듬었습니다(2주차). 정확도 0.5 미만이던 7개 성분 중 6개를 0.85 이상으로 올렸고, 아스타잔틴은 0.60에서 멈췄습니다(먹는 아스타잔틴의 전신 건강 리뷰가 섞임). 표본이 20편이라 정확도에는 ±20%p 정도 오차가 있습니다. 성분별 근거는 `config/keywords.csv`의 `noise_note`(`[검수 11/19]`, `[검수 11/19-2]`, `[검수 11/19-3]`)와 `data/review/`에 있습니다.
- 정확도 0.5~0.8인 CICA·RICE·MUGWORT·HEARTLEAF·EXOSOME·EGCG·RECOMB_COLLAGEN은 뚜렷한 오류 패턴이 없어 검색식을 유지했습니다.
- 푸코잔틴은 검색식을 좁힌 뒤 논문이 39편(연 3~4편)뿐이라 월별이 아니라 연도별로만 봅니다.
- PubMed 논문 수는 출판일이 아니라 PubMed 등록일 기준으로 셉니다. 출판일 기준으로 월별로 세면 온라인 선공개일과 정식 출판일이 다른 논문이 두 번 세어졌습니다(레티놀: 전체 418편인데 월별 합계 630편). 등록일은 출판일보다 보통 몇 주~몇 달 늦을 수 있어 월 단위 시점 해석에 주의합니다.
- 1주차 수집(출판일 기준)에서는 연도만 있는 논문이 1월로 몰려 1월 값이 튀었습니다. 등록일 기준으로 바꾼 뒤에도 분석 때는 연도별 합계나 12개월 이동합계를 함께 봅니다.
- 푸코잔틴·아스타잔틴·재조합 콜라겐은 네이버 검색량이 거의 0이라 소비자 지표로 판단하기 어렵고, 논문·특허 위주로 판단합니다.
