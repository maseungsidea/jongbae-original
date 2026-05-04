"""
기관/외인 수급 트렌드 데이터 생성 스크립트 (all_institutional_trend_data.py)

pykrx로 KOSPI + KOSDAQ 전 종목의 최근 60일 외인/기관 순매수 데이터를
수집하여 data/all_institutional_trend_data.csv 로 저장합니다.

사용법:
    python all_institutional_trend_data.py

출력 파일:
    data/all_institutional_trend_data.csv
    컬럼: ticker, date, foreign_net, inst_net, individual_net

실행 시간: 약 5~10분
⚠ 실행 전에 create_kr_stock_list.py 를 먼저 실행하세요.
"""

import logging
import sys
import time
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import pandas as pd
import pykrx.stock as stock

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

STOCK_LIST_PATH = ROOT / "data" / "korean_stocks_list.csv"
OUTPUT_PATH = ROOT / "data" / "all_institutional_trend_data.csv"

# 수집 기간 (일)
LOOKBACK_DAYS = 60


def fetch_institutional_data(market: str, start: str, end: str) -> pd.DataFrame:
    """
    특정 시장의 전 종목 수급 데이터를 가져옵니다.

    pykrx의 get_market_net_purchases_of_equities_by_ticker()는
    기간 합계를 반환하므로, 일별 데이터가 필요하면 날짜를 반복해야 합니다.
    여기서는 기간 합계 데이터를 사용합니다.
    """
    try:
        df = stock.get_market_net_purchases_of_equities_by_ticker(start, end, market)
        if df is None or df.empty:
            return pd.DataFrame()

        df = df.rename(columns={
            "외국인": "foreign_net",
            "기관합계": "inst_net",
            "개인": "individual_net",
        })
        df["ticker"] = df.index.astype(str)
        df["market"] = market
        df = df.reset_index(drop=True)

        cols = ["ticker", "market", "foreign_net", "inst_net", "individual_net"]
        available = [c for c in cols if c in df.columns]
        return df[available]

    except Exception as e:
        logger.error(f"[{market}] 수급 데이터 오류: {e}")
        return pd.DataFrame()


def collect_institutional_data() -> None:
    """
    KOSPI + KOSDAQ 수급 데이터를 수집하여 CSV 저장.
    """
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    end = date.today()
    start = end - timedelta(days=LOOKBACK_DAYS)
    start_str = start.strftime("%Y%m%d")
    end_str = end.strftime("%Y%m%d")

    logger.info(f"수급 데이터 수집 시작: {start_str} ~ {end_str}")

    frames = []
    for market in ["KOSPI", "KOSDAQ"]:
        logger.info(f"[{market}] 수집 중...")
        df = fetch_institutional_data(market, start_str, end_str)
        if not df.empty:
            frames.append(df)
            logger.info(f"  → {len(df)}개 종목")
        time.sleep(1)  # 시장 간 대기

    if not frames:
        logger.warning("수집된 수급 데이터가 없습니다.")
        return

    result = pd.concat(frames, ignore_index=True)
    result.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")

    logger.info(f"✅ 저장 완료: {OUTPUT_PATH} (총 {len(result):,}개 종목)")


if __name__ == "__main__":
    collect_institutional_data()
