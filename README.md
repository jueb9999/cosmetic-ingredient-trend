# 선행지표 기반 화장품 성분 트렌드 예측

PDRN이 유행하기 전에 어떤 데이터가 먼저 움직였는지 찾고, 같은 신호를 보이는 다음 후보 성분을 찾는 프로젝트입니다.
## 진행 상황

| 주차 | 내용 | 상태 |
|---|---|---|
| 1주차 | 키워드 사전 초안, 네이버 검색량·PubMed 논문 수 수집, 키워드 검수 1회차 | 완료 |
| 2주차 | 검색어 다듬기(검색식 정확도 점검), README 정리 | 완료 |
| 3주차 | KIPRIS 특허 수집·필터 점검, 세 데이터 통합 | 완료 |
| 4주차 | 시작점(onset)·시차·교차상관·그랜저 인과 분석 | 완료 |
| 5주차 | 후보 성분 점수화 | 예정 |

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
│   ├── collect_kipris.py    # KIPRIS 특허 월별 출원 수 수집 (화장품 IPC 필터, 식물성 PDRN 판정)
│   ├── review_kipris.py     # 특허 필터 정확도 점검 (무작위 표본 O/X)
│   ├── build_dataset.py     # 논문·특허·검색량을 하나의 표로 합치기
│   ├── analyze_lead_lag.py  # 시작점·시차·교차상관·그랜저 인과 분석
│   └── quick_plot.py        # 수집 결과 확인용 그래프
├── data/raw/                # 수집 원본 (파일명에 수집 날짜)
├── data/processed/          # 합친 표(trend_long.csv), 분석 결과, 그래프
├── data/review/             # 정확도 점검 결과 (특허 점검 표본은 요약문이 들어 있어 올리지 않음)
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
| `KIPRIS_API_KEY` | 필수(특허) | KIPRIS Plus(plus.kipris.or.kr) 회원가입 > 특허·실용신안 정보 검색 서비스를 **무료**로 신청 > 마이페이지 > APIKEY 관리의 REST AccessKey. 무료는 월 1,000회 호출 (전체 수집 약 70회) |

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

### 5. 특허 수집과 필터 점검

```bash
python src/collect_kipris.py --dry-run    # 검색어 확인
python src/collect_kipris.py              # 전체 수집 (약 70회 호출, 결과는 data/raw/kipris_cache/에 저장되어 다시 실행하면 0회)

python src/review_kipris.py               # 화장품 IPC 필터·식물성 PDRN 판정 점검 표본 만들기
python src/review_kipris.py --summary data/review/kipris_review_<날짜>.csv
```

### 6. 데이터 합치기와 시차 분석

```bash
python src/build_dataset.py      # -> data/processed/trend_long.csv
python src/analyze_lead_lag.py   # -> data/processed/onsets.csv, lead_lag.csv, w4_onsets_train.png
```

## 데이터 설명

| 파일 | 컬럼 | 설명 |
|---|---|---|
| `naver_<날짜>.csv` | ratio | 네이버가 준 원래 값 (그 요청 안에서 최댓값 = 100) |
| | value_scaled | 앵커(히알루론산) 평균 = 100으로 다시 맞춘 값. **성분끼리 비교할 때는 이 값을 사용** |
| `naver_raw_<날짜>.json` | | API 원본 응답 (가공 방식을 바꿀 때 재호출 없이 사용) |
| `pubmed_<날짜>.csv` | value | 그 달에 PubMed에 등록된 논문 수 (등록일 기준이라 한 논문은 한 달에만 세어짐) |
| `kipris_<날짜>.csv` | source | `kipris_cosmetic`: 화장품 IPC 특허 (**주 지표**) / `kipris_all`: 검색어가 들어간 전체 특허 (보조) |
| | value | 그 달에 **출원**된 특허 수 |
| `processed/trend_long.csv` | stage, source | science(pubmed) / patent(kipris_cosmetic, kipris_all) / consumer(naver) |
| | value, value_type | 논문·특허는 건수(count), 네이버는 히알루론산 평균 = 100 기준 지수(index) |
| | provisional | True = 아직 공개되지 않은 출원이 있어 덜 채워진 특허 값 (마지막 18개월) |
| `processed/onsets.csv` | onset_yoy, onset_cp | 지표별 본격 상승 시작 달 (전년 대비 규칙 / 변화점 탐지) |
| `processed/lead_lag.csv` | lag_onset_*, ccf_best_lag, granger_* | 앞 지표가 몇 달 먼저였는지 (양수 = 논문·특허가 먼저) |

### 특허를 세는 기준
- 성분 이름(여러 표기, `keywords.csv`의 `kipris_keywords`)이 제목·요약에 들어간 특허를 출원월 기준으로 셉니다. 같은 특허는 성분마다 한 번만 셉니다.
- **화장품 특허**: IPC가 A61K 8/(화장품 성분) 또는 A61Q(화장품 용도)인 특허. 단 A61Q 중 11(치약·구강용)만 있는 특허는 뺍니다.
- **식물성 PDRN**: PDRN 특허 중 "OO 유래 PDRN", "OO으로부터 추출한 DNA"처럼 출처가 식물·해조류로 적힌 특허. 연어·미생물·줄기세포 유래는 제외합니다.

## 4주차 결과: 논문·특허가 검색보다 먼저 움직였나?

학습용 성분 4개로 확인했습니다. 시차는 개월 단위이고 양수면 논문·특허가 먼저입니다.

| 성분 | 그래프로 본 모습 | 특허 → 검색 시차 (시작점 / 교차상관) | 판단 |
|---|---|---|---|
| 나이아신아마이드 | 특허 2016년, 논문 2016년부터 꾸준히 증가 → 검색 2023년 급등 | +84개월 / +24개월 | **앞섬** |
| 레티놀 | 특허·논문 2018~2019년 상승 → 검색 2021~2022년 상승 | +41개월 / +11개월 | **앞섬** |
| PDRN | 검색 2022년 중반 → 화장품 특허 2023년 → 논문 2025년 | -7개월 / -5개월 | 검색이 먼저 |
| 시카 | 특허가 2012년부터 꾸준히 증가, 검색은 2018년에 한 번 튐 | 판단 불가 | 네이버 데이터가 2016년부터라 검색 시작 시점을 알 수 없음 |

- **H1(일정한 시차로 먼저 움직인다)은 일부만 맞습니다.** 4개 중 2개(나이아신아마이드, 레티놀)에서 특허·논문이 검색보다 1~7년 먼저 올랐지만, 시차가 성분마다 크게 다르고 방법(시작점, 교차상관)에 따라서도 달라 "N개월 뒤 뜬다"처럼 한 숫자로 예측하기는 어렵습니다.
- **PDRN은 반대였습니다.** 소비자 관심이 피부과 시술(연어 주사)에서 먼저 생기고, 화장품 특허와 논문이 그 뒤를 따랐습니다. 필러·주사제를 포함한 전체 특허로 봐도 2023년 중반에 올라 검색보다 늦었습니다. 즉 성분이 뜨는 길은 '연구 → 특허 → 소비자' 한 가지가 아니라 '시술 → 소비자 → 화장품 특허'도 있습니다.
- **그랜저 인과 검정**은 12개 시차를 여러 번 시험한 것을 보정하면 시카(특허 → 검색)만 유의했습니다. 다른 성분은 통계적으로 "특허를 알면 검색을 더 잘 맞힌다"고 말할 근거가 약합니다.
- 그래서 5주차 점수화에서는 정확한 시차로 날짜를 예측하기보다 **"특허·논문은 이미 오르는데 검색은 아직 낮은 성분"(H2)**을 찾는 방향으로 씁니다.

## 알아둘 한계
- 네이버 검색량은 절대 검색 수가 아니라 상대지수입니다. 앵커로 맞춰도 앵커보다 훨씬 작은 성분은 소수점 단위 오차가 커집니다.
- 검색량이 너무 적은 달은 네이버가 값을 주지 않아 0으로 채웠습니다.
- PubMed 검색식은 무작위 20편 O/X 점검을 최대 3차까지 거쳐 다듬었습니다(2주차). 정확도 0.5 미만이던 7개 성분 중 6개를 0.85 이상으로 올렸고, 아스타잔틴은 0.60에서 멈췄습니다(먹는 아스타잔틴의 전신 건강 리뷰가 섞임). 표본이 20편이라 정확도에는 ±20%p 정도 오차가 있습니다. 성분별 근거는 `config/keywords.csv`의 `noise_note`(`[검수 11/19]`, `[검수 11/19-2]`, `[검수 11/19-3]`)와 `data/review/`에 있습니다.
- 정확도 0.5~0.8인 CICA·RICE·MUGWORT·HEARTLEAF·EXOSOME·EGCG·RECOMB_COLLAGEN은 뚜렷한 오류 패턴이 없어 검색식을 유지했습니다.
- 푸코잔틴은 검색식을 좁힌 뒤 논문이 39편(연 3~4편)뿐이라 월별이 아니라 연도별로만 봅니다.
- PubMed 논문 수는 출판일이 아니라 PubMed 등록일 기준으로 셉니다. 출판일 기준으로 월별로 세면 온라인 선공개일과 정식 출판일이 다른 논문이 두 번 세어졌습니다(레티놀: 전체 418편인데 월별 합계 630편). 등록일은 출판일보다 보통 몇 주~몇 달 늦을 수 있어 월 단위 시점 해석에 주의합니다.
- 1주차 수집(출판일 기준)에서는 연도만 있는 논문이 1월로 몰려 1월 값이 튀었습니다. 등록일 기준으로 바꾼 뒤에도 분석 때는 연도별 합계나 12개월 이동합계를 함께 봅니다.
- 푸코잔틴·아스타잔틴·재조합 콜라겐은 네이버 검색량이 거의 0이라 소비자 지표로 판단하기 어렵고, 논문·특허 위주로 판단합니다.
- 특허는 출원 후 약 18개월 뒤에 공개됩니다. 그래서 최근 18개월(현재 2025-05 이후) 특허 수는 실제보다 적고, 분석에서는 빼고 계산합니다(`provisional`).
- 화장품 IPC 필터는 무작위 표본(성분당 화장품 10건·기타 5건) O/X 점검에서 21개 중 16개 성분이 정확도 0.8 이상이었습니다. 아스타잔틴·마이크로바이옴·재조합 콜라겐·후코잔틴(0.5~0.7)은 원료 생산·균주 특허가 섞여 있습니다. 필러·리프팅 실 같은 시술용 특허는 화장품 IPC가 아니라서 빠집니다. 결과는 `data/review/kipris_precision_<날짜>.csv`에 있습니다.
- 식물성 PDRN 판정은 표본 20건(식물 15, 비식물 5)에서 모두 맞았습니다.
- 특허 원문 목록(`kipris_items_*.csv`)과 특허 점검 표본은 요약문 원문이 들어 있어 GitHub에 올리지 않습니다. 수집 스크립트를 실행하면 다시 만들어집니다.
- 시작점은 12개월 합계·전년 대비로 잡기 때문에 실제보다 몇 달 늦게 잡힙니다. 모든 지표에 같이 적용되므로 지표 사이 시차에는 영향이 적습니다.
- 네이버 데이터가 2016-01부터라 검색 시작점은 2017-12보다 앞서 잡을 수 없습니다(`censored`). 시카처럼 그 전에 이미 뜬 성분은 시차를 잴 수 없습니다.
- 변화점 탐지는 ruptures 패키지가 Python 3.14를 아직 지원하지 않아 같은 원리(그래프를 직선 몇 개로 나누기)를 numpy로 직접 구현했습니다.
- 학습용 성분이 4개뿐이라 시차 결론은 일반화하기 어렵습니다. 상관·그랜저 결과는 "먼저 움직인다"는 관계일 뿐 원인이라는 뜻은 아닙니다.
