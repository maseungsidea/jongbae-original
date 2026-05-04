"""
한국 주식 전 종목 목록 생성 스크립트 (scripts/create_kr_stock_list.py)

pykrx로 KOSPI + KOSDAQ 전 종목의 티커, 이름, 시장, 섹터를 수집하여
data/korean_stocks_list.csv 로 저장합니다.

사용법:
    python scripts/create_kr_stock_list.py

출력 파일:
    data/korean_stocks_list.csv
    컬럼: ticker, name, market, sector

실행 시간: 약 1~2분 (pykrx API 호출 포함)
"""

import logging
import sys
import time
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가 (scripts/ 에서 실행하는 경우 대비)
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
import pykrx.stock as stock

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# 출력 경로
OUTPUT_PATH = ROOT / "data" / "korean_stocks_list.csv"


def fetch_tickers(market: str) -> list[dict]:
    """
    특정 시장(KOSPI 또는 KOSDAQ)의 전 종목 티커·이름·섹터를 가져옵니다.

    pykrx의 업종 분류는 완벽하지 않으므로 섹터가 비어있을 수 있습니다.
    """
    from datetime import date
    today = date.today().strftime("%Y%m%d")

    logger.info(f"[{market}] 티커 목록 조회 중...")
    tickers = stock.get_market_ticker_list(today, market=market)

    rows = []
    for i, ticker in enumerate(tickers):
        try:
            name = stock.get_market_ticker_name(ticker)
            # 섹터 정보 (pykrx 0.0.60+ 지원)
            try:
                sector = stock.get_market_sector_classifications(today, market=market)
                ticker_sector = str(sector.get(ticker, ""))
            except Exception:
                ticker_sector = ""

            rows.append({
                "ticker": ticker,
                "name": name,
                "market": market,
                "sector": ticker_sector,
            })

            # 진행상황 표시 & 요청 간격
            if (i + 1) % 100 == 0:
                logger.info(f"  {i + 1}/{len(tickers)} 처리 완료")
            time.sleep(0.05)  # 너무 빠른 요청 방지

        except Exception as e:
            logger.warning(f"  [{ticker}] 스킵: {e}")

    return rows


def create_stock_list() -> None:
    """
    KOSPI + KOSDAQ 전 종목 목록을 CSV로 저장합니다.
    """
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    all_rows = []
    for market in ["KOSPI", "KOSDAQ"]:
        rows = fetch_tickers(market)
        all_rows.extend(rows)
        logger.info(f"[{market}] {len(rows)}개 종목 수집 완료")

    df = pd.DataFrame(all_rows, columns=["ticker", "name", "market", "sector"])
    df = df.drop_duplicates(subset=["ticker"])
    df.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")

    logger.info(f"✅ 저장 완료: {OUTPUT_PATH} (총 {len(df)}개 종목)")


if __name__ == "__main__":
    create_stock_list()
