"""한국 주식 시장 유틸리티 (engine/market_utils.py).

거래일 판별 등 시장 캘린더 관련 헬퍼.
"""
from __future__ import annotations

import datetime
import logging

logger = logging.getLogger(__name__)


def is_trading_day(d: datetime.date | None = None) -> bool:
    """오늘(또는 지정 날짜)이 한국 주식 거래일인지 판별.

    판별 순서:
      1) 주말(토·일) → False
      2) pykrx 삼성전자(005930) 당일 데이터 존재 여부 → 공휴일 대체 포함 판별
         (pykrx 조회 실패 시 True 로 fallback — false negative 허용)
    """
    if d is None:
        d = datetime.date.today()

    if d.weekday() >= 5:  # 5=토, 6=일
        return False

    try:
        import pykrx.stock as pk_stock
        date_str = d.strftime("%Y%m%d")
        df = pk_stock.get_market_ohlcv_by_date(date_str, date_str, "005930")
        if df is None or df.empty:
            logger.info(f"[market_utils] {d} pykrx 데이터 없음 → 휴장일 판정")
            return False
        return True
    except Exception as e:
        logger.warning(f"[market_utils] 거래일 확인 실패 ({e}) → 개장 가정으로 진행")
        return True
