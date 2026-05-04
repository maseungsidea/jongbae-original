"""
전 종목 2년치 일봉 데이터 생성 스크립트 (scripts/create_complete_daily_prices.py)

pykrx로 KOSPI + KOSDAQ 전 종목의 일봉 OHLCV 데이터를 수집하여
data/daily_prices.csv 로 저장합니다.

사용법:
    python scripts/create_complete_daily_prices.py [--days 730]

출력 파일:
    data/daily_prices.csv
    컬럼: ticker, date, open, high, low, close, volume

실행 시간: 약 30분~1시간 (종목 수 × API 호출 시간)
⚠ 실행 전에 create_kr_stock_list.py 를 먼저 실행하세요.
"""

import argparse
import logging
import sys
import time
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
import pykrx.stock as stock

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

STOCK_LIST_PATH = ROOT / "data" / "korean_stocks_list.csv"
OUTPUT_PATH = ROOT / "data" / "daily_prices.csv"


def fetch_daily_prices(ticker: str, start: str, end: str) -> pd.DataFrame:
    """
    단일 종목의 일봉 OHLCV 데이터를 pykrx로 가져옵니다.
    컬럼명을 영문 소문자로 정규화합니다.
    """
    try:
        df = stock.get_market_ohlcv_by_date(start, end, ticker)
        if df is None or df.empty:
            return pd.DataFrame()

        df = df.rename(columns={
            "시가": "open", "고가": "high", "저가": "low",
            "종가": "close", "거래량": "volume", "거래대금": "trading_value"
        })
        df["ticker"] = ticker
        df["date"] = df.index.strftime("%Y-%m-%d")
        df = df.reset_index(drop=True)

        return df[["ticker", "date", "open", "high", "low", "close", "volume"]]
    except Exception as e:
        logger.debug(f"[{ticker}] 오류: {e}")
        return pd.DataFrame()


def create_daily_prices(days: int = 730) -> None:
    """
    전 종목의 일봉 데이터를 수집하여 CSV로 저장합니다.

    이미 OUTPUT_PATH 파일이 있으면 마지막 날짜 이후 데이터만 추가합니다.
    (증분 업데이트 지원)
    """
    if not STOCK_LIST_PATH.exists():
        logger.error(f"종목 목록 파일 없음: {STOCK_LIST_PATH}")
        logger.error("먼저 scripts/create_kr_stock_list.py 를 실행하세요.")
        sys.exit(1)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    stock_df = pd.read_csv(STOCK_LIST_PATH, dtype={"ticker": str})
    tickers = stock_df["ticker"].tolist()

    end = date.today()
    start = end - timedelta(days=days)

    # 증분 업데이트: 기존 파일의 마지막 날짜 이후만 수집
    existing_df = pd.DataFrame()
    if OUTPUT_PATH.exists():
        existing_df = pd.read_csv(OUTPUT_PATH, dtype={"ticker": str})
        if not existing_df.empty and "date" in existing_df.columns:
            last_date = pd.to_datetime(existing_df["date"].max()).date()
            if last_date >= end:
                logger.info("✅ 이미 최신 데이터입니다.")
                return
            start = last_date + timedelta(days=1)
            logger.info(f"증분 업데이트: {start} ~ {end}")

    logger.info(f"총 {len(tickers)}개 종목 수집 시작: {start} ~ {end}")

    all_frames = [existing_df] if not existing_df.empty else []
    for i, ticker in enumerate(tickers):
        df = fetch_daily_prices(ticker, start.strftime("%Y%m%d"), end.strftime("%Y%m%d"))
        if not df.empty:
            all_frames.append(df)

        if (i + 1) % 100 == 0:
            logger.info(f"  {i + 1}/{len(tickers)} 처리 완료")

        time.sleep(0.1)  # KRX 서버 부하 방지

    if not all_frames:
        logger.warning("수집된 데이터가 없습니다.")
        return

    result = pd.concat(all_frames, ignore_index=True)
    result = result.drop_duplicates(subset=["ticker", "date"])
    result = result.sort_values(["ticker", "date"])
    result.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")

    logger.info(f"✅ 저장 완료: {OUTPUT_PATH} (총 {len(result):,}행)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="전 종목 일봉 데이터 생성")
    parser.add_argument("--days", type=int, default=730, help="수집 기간 (기본: 730일)")
    args = parser.parse_args()
    create_daily_prices(days=args.days)
