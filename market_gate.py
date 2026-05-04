"""
Market Gate 분석 모듈 (market_gate.py)

섹터 ETF 7개와 KOSPI200 기술적 지표(EMA, RSI, MACD, 거래량, RS)를
기반으로 시장 진입 가능 여부를 GREEN / YELLOW / RED로 판단합니다.

GREEN(70~100) → 공격적 진입 허용
YELLOW(50~69) → 경계, 소규모 진입만
RED(0~49)    → 현금 보유, 신규 진입 금지

사용법:
    from market_gate import run_kr_market_gate
    result = run_kr_market_gate()
    print(result.gate, result.score)
"""

from __future__ import annotations

# ── matplotlib mock ──────────────────────────────────────────────────────────
# pykrx가 matplotlib를 한글 폰트 설정에만 사용하고 데이터 수집에는 미사용.
# matplotlib 미설치 환경에서도 동작하도록 어떤 속성 접근도 허용하는 AutoMock 삽입.
import sys
import types as _types

class _AutoMock:
    """어떤 속성 접근, 호출, 이터레이션, 할당도 허용하는 범용 Mock 객체."""
    def __init__(self, *a, **kw): pass
    def __call__(self, *a, **kw): return _AutoMock()
    def __getattr__(self, name): return _AutoMock()
    def __setattr__(self, name, val): pass
    def __setitem__(self, key, val): pass
    def __getitem__(self, key): return _AutoMock()
    def __iter__(self): return iter([])
    def __bool__(self): return True
    def __len__(self): return 0
    def __repr__(self): return "<AutoMock>"

def _mock_matplotlib():
    """matplotlib가 없는 환경에서 pykrx가 동작하도록 AutoMock 모듈을 등록합니다."""
    if "matplotlib" in sys.modules and hasattr(sys.modules["matplotlib"], "__file__"):
        return  # 실제 matplotlib가 설치된 경우 스킵

    def _make_mock_module(name: str):
        mod = _types.ModuleType(name)
        mod.__path__ = []
        mod.__package__ = name.split(".")[0]
        # 모든 속성 접근을 AutoMock으로 위임
        mod.__class__ = type("AutoMockModule", (_types.ModuleType,), {
            "__getattr__": lambda self, n: _AutoMock()
        })
        return mod

    for mod_name in [
        "matplotlib",
        "matplotlib.font_manager",
        "matplotlib.pyplot",
        "matplotlib.ticker",
        "matplotlib.axes",
        "matplotlib.figure",
    ]:
        sys.modules.setdefault(mod_name, _make_mock_module(mod_name))

_mock_matplotlib()
# ─────────────────────────────────────────────────────────────────────────────



import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class SectorResult:
    """개별 섹터 ETF 분석 결과"""
    name: str
    ticker: str
    signal: str         # bullish | bearish | neutral
    change_1d: float    # 당일 등락률 (%)
    score: int          # 섹터 기여 점수 (0~15)


@dataclass
class MarketGateResult:
    """Market Gate 전체 분석 결과"""
    gate: str                   # GREEN | YELLOW | RED
    score: int                  # 0~100점
    reasons: List[str] = field(default_factory=list)
    sectors: List[SectorResult] = field(default_factory=list)
    metrics: Dict[str, float] = field(default_factory=dict)
    analysis_date: Optional[date] = None

    def to_dict(self) -> dict:
        return {
            "gate": self.gate,
            "score": self.score,
            "reasons": self.reasons,
            "sectors": [
                {
                    "name": s.name, "ticker": s.ticker,
                    "signal": s.signal, "change_1d": s.change_1d, "score": s.score
                }
                for s in self.sectors
            ],
            "metrics": self.metrics,
            "analysis_date": self.analysis_date.isoformat() if self.analysis_date else None,
        }


# 섹터 ETF 정의 (ticker → 이름)
SECTOR_ETF_MAP = {
    "069500": "KOSPI200",
    "091160": "반도체",
    "305720": "2차전지",
    "091230": "자동차",
    "266360": "IT",
    "091220": "은행",
    "010140": "철강(POSCO)",
}


def _get_ohlcv(ticker: str, days: int = 120) -> Optional[pd.DataFrame]:
    """pykrx로 일봉 데이터를 가져옵니다."""
    try:
        import pykrx.stock as stock
        end = date.today()
        start = end - timedelta(days=days)
        df = stock.get_market_ohlcv_by_date(
            start.strftime("%Y%m%d"),
            end.strftime("%Y%m%d"),
            ticker,
        )
        if df is None or len(df) < 20:
            return None
        return df
    except Exception as e:
        logger.warning(f"[MarketGate] {ticker} 데이터 조회 오류: {e}")
        return None


def _calc_ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _calc_rsi(series: pd.Series, period: int = 14) -> float:
    """RSI 계산 (최근 값만 반환)"""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean().iloc[-1]
    avg_loss = loss.rolling(period).mean().iloc[-1]
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _analyze_single_etf(ticker: str, name: str) -> SectorResult:
    """
    단일 섹터 ETF를 분석하여 SectorResult를 반환합니다.

    bullish: 당일 등락률 > 0 이고 EMA20 > EMA60
    bearish: 당일 등락률 < -1% 이거나 EMA20 < EMA60
    """
    df = _get_ohlcv(ticker, days=120)
    if df is None:
        return SectorResult(name=name, ticker=ticker, signal="neutral", change_1d=0.0, score=5)

    closes = df["종가"]
    change_1d = float(df["등락률"].iloc[-1]) if "등락률" in df.columns else 0.0

    ema20 = _calc_ema(closes, 20).iloc[-1]
    ema60 = _calc_ema(closes, 60).iloc[-1]

    if change_1d > 0 and ema20 > ema60:
        signal = "bullish"
        score = 10
    elif change_1d < -1 or ema20 < ema60:
        signal = "bearish"
        score = 0
    else:
        signal = "neutral"
        score = 5

    return SectorResult(name=name, ticker=ticker, signal=signal, change_1d=change_1d, score=score)


def _analyze_main_index(ticker: str = "069500") -> Dict[str, float]:
    """
    KOSPI200 ETF 기준으로 핵심 기술적 지표를 분석합니다.

    반환 지표 (0~25점 각각):
    - trend_score  : EMA20 > EMA60 여부 (25점)
    - rsi_score    : RSI 50~70 최적 (25점)
    - macd_score   : MACD 골든크로스 (20점)
    - volume_score : 20일 평균 대비 거래량 (15점)
    - rs_score     : 상대강도 (15점)
    """
    scores = {
        "trend_score": 0.0,
        "rsi_score": 0.0,
        "macd_score": 0.0,
        "volume_score": 0.0,
        "rs_score": 0.0,
        "rsi_value": 50.0,
        "ema20": 0.0,
        "ema60": 0.0,
    }

    df = _get_ohlcv(ticker, days=120)
    if df is None:
        return scores

    closes = df["종가"]
    volumes = df["거래량"] if "거래량" in df.columns else pd.Series([1])

    # 추세 정렬 (EMA20 > EMA60)
    ema20 = _calc_ema(closes, 20)
    ema60 = _calc_ema(closes, 60)
    scores["ema20"] = float(ema20.iloc[-1])
    scores["ema60"] = float(ema60.iloc[-1])
    scores["trend_score"] = 25.0 if ema20.iloc[-1] > ema60.iloc[-1] else 0.0

    # RSI 분석 (50~70 = 최적 상승 구간)
    rsi = _calc_rsi(closes)
    scores["rsi_value"] = round(rsi, 1)
    if 50 <= rsi <= 70:
        scores["rsi_score"] = 25.0
    elif 40 <= rsi < 50 or 70 < rsi <= 80:
        scores["rsi_score"] = 12.0
    else:
        scores["rsi_score"] = 0.0

    # MACD 골든크로스
    ema12 = _calc_ema(closes, 12)
    ema26 = _calc_ema(closes, 26)
    macd = ema12 - ema26
    signal_line = _calc_ema(macd, 9)
    if macd.iloc[-1] > signal_line.iloc[-1] and macd.iloc[-2] <= signal_line.iloc[-2]:
        scores["macd_score"] = 20.0  # 골든크로스 발생
    elif macd.iloc[-1] > signal_line.iloc[-1]:
        scores["macd_score"] = 10.0  # 크로스 없지만 MACD > Signal
    else:
        scores["macd_score"] = 0.0

    # 거래량 분석 (20일 평균 대비)
    vol_ratio = volumes.iloc[-1] / volumes.iloc[-20:].mean() if len(volumes) >= 20 else 1.0
    if vol_ratio >= 1.5:
        scores["volume_score"] = 15.0
    elif vol_ratio >= 1.0:
        scores["volume_score"] = 7.0
    else:
        scores["volume_score"] = 0.0

    # 상대강도: 최근 20일 퍼포먼스 기준
    if len(closes) >= 20:
        rs_20d = (closes.iloc[-1] / closes.iloc[-20] - 1) * 100
        if rs_20d > 5:
            scores["rs_score"] = 15.0
        elif rs_20d > 0:
            scores["rs_score"] = 7.0
        else:
            scores["rs_score"] = 0.0

    return scores


def run_kr_market_gate() -> MarketGateResult:
    """
    KR 마켓 게이트 분석을 실행합니다.

    총점 = 메인 지수 점수(trend+rsi+macd+volume+rs) + 섹터 보정
    100점 만점 기준:
    - 70+ → GREEN
    - 50~69 → YELLOW
    - 49 이하 → RED
    """
    reasons: List[str] = []

    # 1. 메인 지수 분석 (KOSPI200 ETF)
    metrics = _analyze_main_index("069500")
    main_score = (
        metrics["trend_score"] + metrics["rsi_score"] +
        metrics["macd_score"] + metrics["volume_score"] + metrics["rs_score"]
    )

    # 2. 섹터 ETF 분석
    sector_results: List[SectorResult] = []
    for ticker, name in SECTOR_ETF_MAP.items():
        if ticker == "069500":  # 메인 지수는 별도 분석
            continue
        sr = _analyze_single_etf(ticker, name)
        sector_results.append(sr)

    bullish_sectors = sum(1 for s in sector_results if s.signal == "bullish")
    bearish_sectors = sum(1 for s in sector_results if s.signal == "bearish")

    # 섹터 보정: 강세 섹터 4+ → +5점, 약세 섹터 과반 → -10점
    sector_bonus = 0
    if bullish_sectors >= 4:
        sector_bonus = 5
        reasons.append(f"강세 섹터 {bullish_sectors}개")
    if bearish_sectors >= 3:
        sector_bonus -= 10
        reasons.append(f"약세 섹터 {bearish_sectors}개")

    # 근거 메시지 생성
    if metrics["trend_score"] > 0:
        reasons.append(f"EMA20({metrics['ema20']:.0f}) > EMA60({metrics['ema60']:.0f})")
    else:
        reasons.append("EMA20 < EMA60 (하락 추세)")

    reasons.append(f"RSI: {metrics['rsi_value']:.1f}")

    total_score = min(100, max(0, int(main_score + sector_bonus)))

    # GREEN / YELLOW / RED 결정
    if total_score >= 70:
        gate = "GREEN"
    elif total_score >= 50:
        gate = "YELLOW"
    else:
        gate = "RED"

    return MarketGateResult(
        gate=gate,
        score=total_score,
        reasons=reasons,
        sectors=sector_results,
        metrics={k: round(v, 2) for k, v in metrics.items()},
        analysis_date=date.today(),
    )
