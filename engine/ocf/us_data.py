"""
미국/글로벌 시장 데이터 수집 (engine/ocf/us_data.py)

yfinance 로 SPY, ^VIX, EWY(미국상장 한국ETF), KRW=X 전일 데이터를
조회해 변화율 dict 로 반환한다.

EWY 를 쓰는 이유:
  미국 거래소 상장이므로 전날 미국 마감(16:00 ET ≈ 06:00 KST) 기준
  한국 시장 야간 센티먼트를 반영. 한국 현물지수(^KS11)는 당일 09:00~
  15:30 KST 데이터라 look-ahead bias 발생 — 사용 금지.

데이터 누락/오류 시 None 반환 — checker 가 None 을 triggered=False 로 처리.
"""
from __future__ import annotations

import datetime
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_TICKERS = {
    "spy": "SPY",
    "vix": "^VIX",
    "ewy": "EWY",       # iShares MSCI South Korea ETF (미국상장 한국 ETF)
    "usdkrw": "KRW=X",
}


def fetch_us_overnight(as_of: Optional[datetime.date] = None) -> dict:
    """전일 종가 기준 변화율 dict 반환.

    반환 키:
        spy_chg_pct    : SPY 전일 등락률 (%)
        vix_close      : VIX 종가 (절대값)
        vix_chg_pct    : VIX 전일 대비 변화율 (%)
        ewy_chg_pct    : EWY(한국 ETF) 전일 등락률 (%)
        usdkrw         : 원/달러 환율 (절대값)
        usdkrw_chg_pct : 원/달러 전일 대비 변화율 (%)
        fetched_at     : ISO 형식 수집 시각
    """
    result: dict = {k: None for k in (
        "spy_chg_pct",
        "vix_close", "vix_chg_pct",
        "ewy_chg_pct",
        "usdkrw", "usdkrw_chg_pct",
        "fetched_at",
    )}
    result["fetched_at"] = datetime.datetime.now().isoformat(timespec="seconds")

    try:
        import yfinance as yf
        import pandas as pd

        tickers_str = " ".join(_TICKERS.values())
        df = yf.download(
            tickers_str,
            period="7d",
            interval="1d",
            progress=False,
            auto_adjust=True,
        )

        if df.empty:
            logger.warning("[OCF/us_data] yfinance 빈 데이터 반환")
            return result

        # MultiIndex 또는 단일 티커 분기
        if isinstance(df.columns, pd.MultiIndex):
            closes = df["Close"]
        else:
            # 단일 티커만 반환됐을 때 — 전체 누락으로 처리
            logger.warning("[OCF/us_data] 단일 티커 응답 — 다중 티커 다운로드 실패")
            return result

        def _chg(ticker_key: str):
            col = _TICKERS[ticker_key]
            if col not in closes.columns:
                logger.warning(f"[OCF/us_data] {col} 데이터 없음")
                return None, None
            s = closes[col].dropna()
            if len(s) < 2:
                return None, None
            prev, last = float(s.iloc[-2]), float(s.iloc[-1])
            if prev == 0:
                return last, None
            return last, (last / prev - 1) * 100

        _, spy_chg = _chg("spy")
        result["spy_chg_pct"] = spy_chg

        vix_v, vix_chg = _chg("vix")
        result["vix_close"] = vix_v
        result["vix_chg_pct"] = vix_chg

        _, ewy_chg = _chg("ewy")
        result["ewy_chg_pct"] = ewy_chg

        usdkrw_v, usdkrw_chg = _chg("usdkrw")
        result["usdkrw"] = usdkrw_v
        result["usdkrw_chg_pct"] = usdkrw_chg

        logger.info(
            f"[OCF/us_data] SPY={spy_chg:+.2f}% EWY={ewy_chg:+.2f}% "
            f"VIX={vix_v:.1f} USDKRW={usdkrw_v:.0f}"
            if all(x is not None for x in [spy_chg, ewy_chg, vix_v, usdkrw_v])
            else "[OCF/us_data] 일부 데이터 누락"
        )

    except Exception as e:
        logger.warning(f"[OCF/us_data] yfinance 조회 실패: {e}")

    return result
