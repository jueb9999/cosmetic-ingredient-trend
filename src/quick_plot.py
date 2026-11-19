"""수집 결과를 그래프로 빠르게 확인하는 스크립트.

실행 예
    python src/quick_plot.py                      # 학습용 성분 4개 (네이버 + PubMed)
    python src/quick_plot.py --ids PDRN EXOSOME   # 원하는 성분만
그래프는 data/processed/check_<날짜>.png로 저장된다.
"""
import argparse

import matplotlib
matplotlib.use("Agg")  # 창을 띄우지 않고 파일로만 저장
import matplotlib.pyplot as plt
import pandas as pd

from common import RAW_DIR, ROOT, load_keywords, today_tag


def latest(prefix):
    """data/raw에서 prefix로 시작하는 가장 최근 CSV를 읽는다."""
    files = sorted(RAW_DIR.glob(f"{prefix}_2*.csv"))
    if not files:
        return None
    print(f"읽는 파일: {files[-1].name}")
    return pd.read_csv(files[-1], encoding="utf-8-sig")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids", nargs="*", help="그릴 성분 ID (기본: 학습용 4개)")
    args = parser.parse_args()
    ids = args.ids or load_keywords(["train"])["ingredient_id"].tolist()

    naver, pubmed = latest("naver"), latest("pubmed")
    panels = [(d, col, title) for d, col, title in [
        (naver, "value_scaled", "Naver search (anchor = 100)"),
        (pubmed, "value", "PubMed papers per month"),
    ] if d is not None]
    if not panels:
        raise SystemExit("data/raw에 수집 결과가 없습니다. 먼저 수집 스크립트를 실행하세요.")

    fig, axes = plt.subplots(len(panels), 1, figsize=(11, 4 * len(panels)), sharex=True, squeeze=False)
    for ax, (df, col, title) in zip(axes[:, 0], panels):
        for i in ids:
            s = df[df["ingredient_id"] == i].set_index("month")[col]
            # 3개월 이동평균으로 들쭉날쭉한 값을 부드럽게
            s.index = pd.PeriodIndex(s.index, freq="M").to_timestamp()
            ax.plot(s.rolling(3, min_periods=1).mean(), label=i)
        ax.set_title(title)
        ax.legend(loc="upper left")
        ax.grid(alpha=0.3)

    out = ROOT / "data" / "processed" / f"check_{today_tag()}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out, dpi=120)
    print(f"그래프 저장: {out}")


if __name__ == "__main__":
    main()
