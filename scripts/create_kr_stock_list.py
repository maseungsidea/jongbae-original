"""
한국 주식 전 종목 목록 생성 스크립트 (scripts/create_kr_stock_list.py)

FinanceDataReader로 KOSPI + KOSDAQ 전 종목의 티커, 이름, 시장, 시총, 종가를
data/korean_stocks_list.csv 로 저장합니다.

(pykrx의 ticker list endpoint가 KRX 로그인 차단으로 빈 응답을 주는 이슈 회피.
OHLCV 조회는 여전히 pykrx가 동작하므로 daily_prices 스크립트는 그대로 사용 가능.)

사용법:
    python scripts/create_kr_stock_list.py

출력 파일:
    data/korean_stocks_list.csv
    컬럼: ticker, name, market, sector, marcap, close
"""

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
import FinanceDataReader as fdr

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

OUTPUT_PATH = ROOT / "data" / "korean_stocks_list.csv"


def fetch_listing(market: str) -> pd.DataFrame:
    logger.info(f"[{market}] FDR StockListing 조회 중...")
    df = fdr.StockListing(market)
    df = df.rename(columns={"Code": "ticker", "Name": "name",
                            "Market": "market", "Marcap": "marcap",
                            "Close": "close"})
    df["sector"] = ""  # FDR 기본 listing에는 섹터 컬럼 없음 — get_sector(ticker)에서 별도 매핑
    cols = ["ticker", "name", "market", "sector", "marcap", "close"]
    df = df[[c for c in cols if c in df.columns]]
    logger.info(f"[{market}] {len(df)}개 종목")
    return df


def create_stock_list() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    frames = [fetch_listing(m) for m in ("KOSPI", "KOSDAQ")]
    df = pd.concat(frames, ignore_index=True)
    df = df.drop_duplicates(subset=["ticker"])
    df.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")

    logger.info(f"✅ 저장 완료: {OUTPUT_PATH} (총 {len(df)}개 종목)")


if __name__ == "__main__":
    create_stock_list()
