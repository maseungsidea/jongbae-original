"""
VCP + 수급 스크리너 (screener.py)

CSV 파일 기반 오프라인 스크리너. pykrx 실시간 API 대신
사전 수집된 daily_prices.csv 와 all_institutional_trend_data.csv 를
사용하여 빠르게 VCP 패턴을 탐지합니다.

주요 특징:
- 100점 만점 채점 (VCP 40 + 수급 30 + 모멘텀 20 + 섹터 10)
- VCP: 볼린저 밴드 수축 + 거래량 감소 + 저항선 내 횡보
- 실시간 API 없이 배치 분석 가능 → 빠른 응답
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd

from app.utils.cache import get_sector

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
PRICES_PATH = ROOT / "data" / "daily_prices.csv"
SUPPLY_PATH = ROOT / "data" / "all_institutional_trend_data.csv"


class SmartMoneyScreener:
    """
    VCP + 수급 기반 스마트머니 스크리너.

    CSV 파일에서 데이터를 로드하여 100점 만점으로 채점합니다.
    """

    def __init__(self):
        self._prices: pd.DataFrame = pd.DataFrame()
        self._supply: pd.DataFrame = pd.DataFrame()
        self._loaded = False

    def _load_data(self) -> bool:
        """CSV 데이터를 메모리에 로드합니다. 실패 시 False 반환."""
        if self._loaded:
            return True

        if not PRICES_PATH.exists():
            logger.warning(f"[Screener] 일봉 데이터 없음: {PRICES_PATH}")
            return False
        if not SUPPLY_PATH.exists():
            logger.warning(f"[Screener] 수급 데이터 없음: {SUPPLY_PATH}")
            return False

        self._prices = pd.read_csv(PRICES_PATH, dtype={"ticker": str})
        self._supply = pd.read_csv(SUPPLY_PATH, dtype={"ticker": str})
        self._loaded = True
        return True

    def run_screening(self, max_stocks: int = 50) -> pd.DataFrame:
        """
        전체 종목 스크리닝을 실행하고 상위 max_stocks 개를 반환합니다.

        Returns:
            채점 결과 DataFrame (컬럼: ticker, name, score, vcp_score, supply_score, ...)
        """
        if not self._load_data():
            return pd.DataFrame()

        tickers = self._prices["ticker"].unique()
        logger.info(f"[Screener] {len(tickers)}개 종목 스크리닝 시작")

        results = []
        for ticker in tickers:
            df_ticker = self._prices[self._prices["ticker"] == ticker].copy()
            df_ticker = df_ticker.sort_values("date")

            if len(df_ticker) < 30:
                continue

            stock_data = {
                "ticker": ticker,
                "sector": get_sector(ticker),
                "close": df_ticker["close"].iloc[-1],
                "volume": df_ticker["volume"].iloc[-1] if "volume" in df_ticker.columns else 0,
                "df": df_ticker,
            }

            score = self._calculate_score(stock_data)
            if score > 0:
                results.append({
                    "ticker": ticker,
                    "sector": stock_data["sector"],
                    "close": stock_data["close"],
                    "total_score": score,
                })

        if not results:
            return pd.DataFrame()

        result_df = pd.DataFrame(results)
        result_df = result_df.sort_values("total_score", ascending=False).head(max_stocks)
        return result_df.reset_index(drop=True)

    def generate_signals(self, results: pd.DataFrame) -> List[Dict]:
        """
        스크리닝 결과 DataFrame을 Flask API 응답 형식으로 변환합니다.
        """
        if results.empty:
            return []

        signals = []
        for _, row in results.iterrows():
            # 수급 데이터 조회
            supply_row = self._supply[self._supply["ticker"] == row["ticker"]]
            foreign_net = int(supply_row["foreign_net"].iloc[0]) if not supply_row.empty and "foreign_net" in supply_row else 0
            inst_net = int(supply_row["inst_net"].iloc[0]) if not supply_row.empty and "inst_net" in supply_row else 0

            signals.append({
                "ticker": row["ticker"],
                "sector": row.get("sector", ""),
                "score": round(float(row["total_score"]), 1),
                "close": float(row["close"]),
                "foreign_net": foreign_net,
                "inst_net": inst_net,
            })

        return signals

    def detect_vcp_pattern(self, df: pd.DataFrame) -> float:
        """
        VCP(Volatility Contraction Pattern) 점수를 계산합니다.

        VCP 조건:
        1. 볼린저 밴드 수축 (BB Width < 5%)
        2. 거래량 감소 추세 (최근 10일 < 20일 평균)
        3. 저항선 내 횡보 (고가/저가 범위 축소)

        Returns:
            0~40 사이의 VCP 점수
        """
        if len(df) < 20:
            return 0

        closes = df["close"].values
        volumes = df["volume"].values if "volume" in df.columns else np.ones(len(df))

        # 볼린저 밴드 수축도
        mean_20 = np.mean(closes[-20:])
        std_20 = np.std(closes[-20:])
        bb_width = (4 * std_20) / mean_20 if mean_20 > 0 else 1.0

        bb_score = max(0, 20 * (1 - bb_width / 0.1))  # 0% 수축 = 20점

        # 거래량 감소
        vol_recent = np.mean(volumes[-10:])
        vol_base = np.mean(volumes[-20:])
        vol_ratio = vol_recent / vol_base if vol_base > 0 else 1.0
        vol_score = 10 * max(0, 1 - vol_ratio) if vol_ratio < 1 else 0

        # 고가-저가 범위 수축
        recent_range = (df["high"].iloc[-10:].max() - df["low"].iloc[-10:].min()) if "high" in df.columns else 0
        base_range = (df["high"].iloc[-20:].max() - df["low"].iloc[-20:].min()) if "high" in df.columns else 1
        range_ratio = recent_range / base_range if base_range > 0 else 1.0
        range_score = 10 * max(0, 1 - range_ratio)

        return min(40, bb_score + vol_score + range_score)

    def _calculate_score(self, stock_data: Dict) -> float:
        """
        100점 만점 채점:
        - VCP 40점
        - 수급 30점
        - 모멘텀 20점
        - 섹터 10점
        """
        df = stock_data["df"]
        ticker = stock_data["ticker"]

        # VCP 채점
        vcp_score = self.detect_vcp_pattern(df)

        # 수급 채점 (30점)
        supply_score = 0
        supply_row = self._supply[self._supply["ticker"] == ticker]
        if not supply_row.empty:
            foreign_net = supply_row["foreign_net"].iloc[0] if "foreign_net" in supply_row else 0
            inst_net = supply_row["inst_net"].iloc[0] if "inst_net" in supply_row else 0
            if foreign_net > 0:
                supply_score += 15
            if inst_net > 0:
                supply_score += 15

        # 모멘텀 채점 (20점)
        momentum_score = 0
        closes = df["close"].values
        if len(closes) >= 60:
            ma20 = np.mean(closes[-20:])
            ma60 = np.mean(closes[-60:])
            if closes[-1] > ma20 > ma60:
                momentum_score = 20

        # 섹터 채점 (10점): 매핑된 섹터면 10점
        sector_score = 10 if stock_data["sector"] else 0

        return vcp_score + supply_score + momentum_score + sector_score
