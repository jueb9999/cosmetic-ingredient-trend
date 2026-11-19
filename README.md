# 선행지표 기반 화장품 성분 트렌드 예측

PDRN이 유행하기 전에 어떤 데이터가 먼저 움직였는지 찾고, 같은 신호를 보이는 다음 후보 성분을 찾는 프로젝트입니다.
지금 단계(1주차)는 **키워드 사전 + 네이버 검색량 + PubMed 논문 수 수집**입니다.

## 폴더 구조

```
cosmetic-ingredient-trend/
├── config/keywords.csv      # 성분별 검색어 사전 (엑셀로 열어서 수정 가능)
├── src/
│   ├── common.py            # 공통 함수
│   ├── collect_naver.py     # 네이버 데이터랩 검색량 수집
│   ├── collect_pubmed.py    # PubMed 월별 논문 수 수집
│   └── quick_plot.py        # 수집 결과 확인용 그래프
├── data/raw/                # 수집 원본 (파일명에 수집 날짜)
├── data/processed/          # 가공 데이터·그래프
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
2. 네이버 Client ID/Secret과 (선택) NCBI API 키를 넣습니다. 발급 방법은 계획 문서의 "1주차 실행 가이드"를 보세요.

### 3. 수집 실행

```bash
python src/collect_naver.py --dry-run     # 요청 계획 확인 (키 없어도 됨)
python src/collect_naver.py               # 네이버 수집 (1분 이내)

python src/collect_pubmed.py --dry-run    # 검색식 확인
python src/collect_pubmed.py --only PDRN --start 2024-01   # 시험 수집
python src/collect_pubmed.py              # 전체 수집 (키 없으면 약 15분)

python src/quick_plot.py                  # 그래프로 확인
```

## 데이터 설명

| 파일 | 컬럼 | 설명 |
|---|---|---|
| `naver_<날짜>.csv` | ratio | 네이버가 준 원래 값 (그 요청 안에서 최댓값 = 100) |
| | value_scaled | 앵커(히알루론산) 평균 = 100으로 다시 맞춘 값. **성분끼리 비교할 때는 이 값을 사용** |
| `naver_raw_<날짜>.json` | | API 원본 응답 (가공 방식을 바꿀 때 재호출 없이 사용) |
| `pubmed_<날짜>.csv` | value | 그 달에 출판된 논문 수 |

## 알아둘 한계
- 네이버 검색량은 절대 검색 수가 아니라 상대지수입니다. 앵커로 맞춰도 앵커보다 훨씬 작은 성분은 소수점 단위 오차가 커집니다.
- 검색량이 너무 적은 달은 네이버가 값을 주지 않아 0으로 채웠습니다.
- PubMed 검색식은 초안입니다. pubmed.ncbi.nlm.nih.gov에 붙여넣어 결과 논문이 화장품·피부 관련인지 직접 확인하고 다듬어야 합니다.
