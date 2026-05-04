"""
루트 설정 모듈 (config.py)

시스템 전체에서 공유되는 Enum, Dataclass 기반 설정값을 정의합니다.
- MarketRegime: 시장 국면 분류
- BacktestConfig: 백테스트 파라미터 (수수료, 손절/익절, 리스크 등)
- ScreenerConfig: VCP 스크리너 파라미터
- TrendThresholds: 추세 판단 기준값
- MarketGateConfig: Market Gate 운용 파라미터
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List


# ─────────────────────────────────────────
# Enum 정의
# ─────────────────────────────────────────

class MarketRegime(Enum):
    """시장 국면: 강세/약세/중립"""
    BULL = "bull"
    BEAR = "bear"
    NEUTRAL = "neutral"


class SignalType(Enum):
    """시그널 종류"""
    VCP = "vcp"           # Volatility Contraction Pattern
    CLOSING_BET = "closing_bet"  # 종가베팅 시그널
    BREAKOUT = "breakout"  # 저항선 돌파


# ─────────────────────────────────────────
# Dataclass 정의
# ─────────────────────────────────────────

@dataclass
class TrendThresholds:
    """
    추세 판단 기준 임계값.

    MA 기반 국면 판단에 사용합니다:
    - price_above_ma200_bull: 종가가 MA200 위에 있으면 강세 국면 판정
    - advance_decline_bull: 등락 비율 기준 (상승 종목 / 전체)
    """
    price_above_ma200_bull: float = 0.55    # 55% 이상 → BULL
    price_above_ma200_bear: float = 0.40    # 40% 미만 → BEAR
    advance_decline_bull: float = 0.55
    advance_decline_bear: float = 0.40
    new_high_bull: int = 100                # 신고가 종목 수 기준
    new_high_bear: int = 30


@dataclass
class MarketGateConfig:
    """
    Market Gate 운용 파라미터.

    총 100점 기준으로 시장 진입 여부를 판단합니다.
    - green_threshold: 진입 허용 (GREEN)
    - yellow_threshold: 경계 (YELLOW)
    - 그 미만: 진입 금지 (RED)
    """
    green_threshold: int = 70
    yellow_threshold: int = 50

    # 섹터 ETF 분석 대상 (pykrx 티커)
    sector_etfs: List[str] = field(default_factory=lambda: [
        "069500",  # KODEX 200 (KOSPI200)
        "091160",  # KODEX 반도체
        "305720",  # KODEX 2차전지산업
        "091230",  # KODEX 자동차
        "266360",  # KODEX IT
        "091220",  # KODEX 은행
        "010140",  # POSCO홀딩스 (철강 프록시)
    ])

    # 지표별 가중치 (합계 100)
    weight_trend: int = 25    # EMA20 > EMA60
    weight_rsi: int = 25      # RSI 50–70 최적
    weight_macd: int = 20     # MACD 골든크로스
    weight_volume: int = 15   # 20일 평균 대비 거래량
    weight_rs: int = 15       # 상대강도(RS)


@dataclass
class BacktestConfig:
    """
    백테스트 파라미터.

    매매 비용(수수료+슬리피지)과 손절/익절, 리스크 비율을 관리합니다.
    팩토리 메서드로 보수적/공격적 프리셋을 제공합니다.
    """
    # 매매 비용 (%)
    commission_pct: float = 0.015   # 증권사 수수료 0.015%
    slippage_pct: float = 0.05      # 슬리피지 0.05%

    # 손절/익절 기준 (%)
    stop_loss_pct: float = 3.0      # -3% 손절
    take_profit_pct: float = 5.0    # +5% 익절

    # 리스크 관리
    r_ratio: float = 0.005          # 계좌 대비 1R 비율 (0.5%)
    max_position_pct: float = 0.20  # 最大 단일 포지션 비율 (20%)
    max_positions: int = 5          # 동시 보유 최대 종목 수

    # 진입 조건: 최소 시장 국면
    allowed_regimes: List[str] = field(
        default_factory=lambda: [MarketRegime.BULL.value, MarketRegime.NEUTRAL.value]
    )

    def get_total_cost_pct(self) -> float:
        """
        왕복(매수+매도) 총 거래비용 비율 반환.
        손절/익절 계산 시 이 값을 손절선에 추가해 실질 손실을 계산합니다.
        """
        return (self.commission_pct + self.slippage_pct) * 2

    def should_trade_in_regime(self, regime: str) -> bool:
        """현재 시장 국면이 매매 허용 범위 내인지 확인"""
        return regime in self.allowed_regimes

    @classmethod
    def conservative(cls) -> "BacktestConfig":
        """
        보수적 설정: 좁은 손절, 낮은 리스크 비율, BULL 국면만 매매.
        초보자나 변동성이 높은 시장에서 권장합니다.
        """
        return cls(
            stop_loss_pct=2.5,
            take_profit_pct=4.0,
            r_ratio=0.003,
            max_positions=3,
            allowed_regimes=[MarketRegime.BULL.value],
        )

    @classmethod
    def aggressive(cls) -> "BacktestConfig":
        """
        공격적 설정: 넓은 손절, 높은 리스크 비율, 중립까지 허용.
        경험 있는 트레이더나 강세장에서 더 높은 수익을 노릴 때 사용합니다.
        """
        return cls(
            stop_loss_pct=4.0,
            take_profit_pct=8.0,
            r_ratio=0.008,
            max_positions=7,
            allowed_regimes=[MarketRegime.BULL.value, MarketRegime.NEUTRAL.value],
        )


@dataclass
class ScreenerConfig:
    """
    VCP + 수급 스크리너 파라미터.

    스크리닝 필터 기준과 점수 가중치를 정의합니다.
    """
    # 기본 필터
    min_trading_value: int = 5_000_000_000   # 최소 거래대금 50억 원
    max_change_pct: float = 15.0             # 당일 급등 제외 기준 (+15% 이상)
    min_close_price: int = 1_000             # 최소 종가 (동전주 제외)

    # VCP 패턴 기준
    vcp_contraction_weeks: int = 3           # 최소 횡보 기간 (주)
    vcp_volume_dry_ratio: float = 0.5        # 거래량 감소 기준 (평균 대비 50%)

    # 수급 기준 (일)
    supply_lookback_days: int = 5            # 외인/기관 순매수 집계 기간

    # 점수 가중치 (합계 100)
    weight_vcp: int = 40
    weight_supply: int = 30
    weight_momentum: int = 20
    weight_sector: int = 10
