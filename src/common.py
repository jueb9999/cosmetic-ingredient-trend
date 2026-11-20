"""두 수집 스크립트가 함께 쓰는 공통 함수 모음."""
from datetime import date
from pathlib import Path

import pandas as pd

# 프로젝트 최상위 폴더 (이 파일 기준으로 한 단계 위)
ROOT = Path(__file__).resolve().parents[1]
KEYWORDS_CSV = ROOT / "config" / "keywords.csv"
RAW_DIR = ROOT / "data" / "raw"


def load_keywords(groups=None):
    """keywords.csv를 읽어서 DataFrame으로 돌려준다.

    groups: ["train", "candidate"]처럼 넘기면 그 그룹만 남긴다.
    """
    df = pd.read_csv(KEYWORDS_CSV, encoding="utf-8-sig")
    df["naver_keywords"] = df["naver_keywords"].str.split("|")
    if groups:
        df = df[df["group"].isin(groups)]
    return df.reset_index(drop=True)


def use_korean_font():
    """그래프 글자를 한국어로 쓰기 위한 글꼴 설정 (윈도우 맑은 고딕, 없으면 다른 한글 글꼴)."""
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    have = {f.name for f in font_manager.fontManager.ttflist}
    for name in ["Malgun Gothic", "Noto Sans KR", "AppleGothic", "NanumGothic"]:
        if name in have:
            plt.rcParams["font.family"] = name
            break
    plt.rcParams["axes.unicode_minus"] = False  # 마이너스 기호 깨짐 방지


def today_tag():
    """파일 이름에 붙일 오늘 날짜 (예: 20261120)."""
    return date.today().strftime("%Y%m%d")


def raw_path(name, ext="csv"):
    """data/raw/<name>_<날짜>.<ext> 경로를 만든다. 폴더가 없으면 만든다."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    return RAW_DIR / f"{name}_{today_tag()}.{ext}"
