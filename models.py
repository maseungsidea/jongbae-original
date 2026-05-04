"""
루트 데이터 모델 모듈 (models.py)

Flask API 응답과 백테스트 결과를 표현하는 Dataclass 모델들을 정의합니다.
- StockInfo: 종목 기본 정보
- InstitutionalFlow: 외인/기관 수급 정보
- TrendAnalysis: 추세 분석 결과
- Signal: 매매 시그널
- Trade: 개별 거래 기록
- BacktestResult: 백테스트 결과 요약
- MarketStatus: 시장 상태 (Market Gate)
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional


# ─────────────────────────────────────────
# 공통 직렬화 믹스인
# ─────────────────────────────────────────

class ToDictMixin:
    """
    to_dict() 기본 구현 믹스인.
    dataclasses.asdict()를 래핑하며, datetime/date → ISO 문자열로 변환합니다.
    """
    def to_dict(self) -> Dict[str, Any]:
        raw = asdict(self)
        return _serialize_dict(raw)


def _serialize_dict(obj: Any) -> Any:
    """재귀적으로 dict 내 datetime/date 객체를 ISO 문자열로 변환"""
    if isinstance(obj, dict):
        return {k: _serialize_dict(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize_dict(v) for v in obj]
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Enum):
        return obj.value
    return obj


# ─────────────────────────────────────────
# 종목 기본 정보
# ─────────────────────────────────────────

@dataclass
class StockInfo(ToDictMixin):
    """
    종목 기본 정보.
    KRX 데이터나 CSV에서 불러온 정적 메타데이터를 담습니다.
    """
    ticker: str
    name: str
    market: str         # KOSPI | KOSDAQ
    sector: str = ""
    industry: str = ""


# ─────────────────────────────────────────
# 수급 데이터
# ─────────────────────────────────────────

@dataclass
class InstitutionalFlow(ToDictMixin):
    """
    외인/기관 수급 데이터.
    5일 누적 순매수를 기준으로 수급 강도를 판단합니다.
    """
    ticker: str
    date: date
    foreign_net_buy_5d: int = 0     # 외인 5일 누적 순매수 (주)
    inst_net_buy_5d: int = 0        # 기관 5일 누적 순매수 (주)
    foreign_net_buy_value: int = 0  # 외인 순매수 금액 (원)
    inst_net_buy_value: int = 0     # 기관 순매수 금액 (원)

    @property
    def is_positive(self) -> bool:
        """외인 또는 기관 중 하나라도 순매수이면 긍정적 수급 판정"""
        return self.foreign_net_buy_5d > 0 or self.inst_net_buy_5d > 0


# ─────────────────────────────────────────
# 추세 분석
# ─────────────────────────────────────────

@dataclass
class TrendAnalysis(ToDictMixin):
    """
    개별 종목 추세 분석 결과.
    MA 정배열, 신고가 여부, 모멘텀 스코어를 포함합니다.
    """
    ticker: str
    analysis_date: date

    # 이동평균 정배열 여부 (MA5 > MA20 > MA60)
    ma_aligned: bool = False

    # 52주 신고가 여부
    is_new_high_52w: bool = False

    # 저항선 돌파 여부
    is_breakout: bool = False

    # 모멘텀 점수 (0~100)
    momentum_score: float = 0.0

    # 현재가의 MA200 대비 위치 (%) — 양수면 MA200 위
    pct_from_ma200: float = 0.0


# ─────────────────────────────────────────
# 매매 시그널
# ─────────────────────────────────────────

@dataclass
class Signal(ToDictMixin):
    """
    종가베팅 매매 시그널.

    이 모델은 API 응답용으로 사용됩니다.
    엔진 내부에서는 engine.models.Signal 을 사용합니다.
    두 모델의 분리 이유: 루트 models.py는 Flask API 계층의 직렬화에 집중하고,
    engine/models.py는 채점 세부 데이터(ScoreDetail, ChecklistDetail)를 포함합니다.
    """
    ticker: str
    name: str
    market: str
    sector: str
    signal_date: date
    grade: str              # S | A | B
    score: int              # 총점 (12점 만점)
    current_price: float
    entry_price: float
    stop_price: float
    target_price: float
    position_size: float    # 투자 금액 (원)
    quantity: int           # 매수 주수
    reason: str = ""        # LLM 또는 룰 기반 진입 근거
    news_summary: str = ""  # 뉴스 핵심 요약


# ─────────────────────────────────────────
# 거래 기록 (백테스트 / 실거래)
# ─────────────────────────────────────────

@dataclass
class Trade(ToDictMixin):
    """
    개별 거래 기록.
    백테스트와 실거래 결과를 동일한 구조로 관리합니다.
    """
    ticker: str
    name: str
    entry_date: date
    entry_price: float
    quantity: int
    stop_price: float
    target_price: float
    r_value: float              # 1R 금액 (손실 허용액)
    grade: str

    # 청산 정보 (None이면 미청산)
    exit_date: Optional[date] = None
    exit_price: Optional[float] = None
    exit_reason: str = ""       # "stop_loss" | "take_profit" | "time_exit" | "manual"

    @property
    def is_closed(self) -> bool:
        """거래가 청산되었으면 True"""
        return self.exit_date is not None and self.exit_price is not None

    @property
    def cost(self) -> float:
        """진입 비용 (세금·수수료 제외, 단순 매수가)"""
        return self.entry_price * self.quantity

    @property
    def return_pct(self) -> float:
        """수익률 (%). 미청산 시 0 반환"""
        if not self.is_closed or self.exit_price is None:
            return 0.0
        return (self.exit_price - self.entry_price) / self.entry_price * 100

    @property
    def pnl(self) -> float:
        """손익 금액 (원). 미청산 시 0 반환"""
        if not self.is_closed or self.exit_price is None:
            return 0.0
        return (self.exit_price - self.entry_price) * self.quantity

    @property
    def r_multiple(self) -> float:
        """
        R 배수: 손익을 1R 기준으로 표준화.
        예) pnl=50,000원, r_value=25,000원 → 2.0R
        """
        if self.r_value == 0:
            return 0.0
        return self.pnl / self.r_value


# ─────────────────────────────────────────
# 백테스트 결과
# ─────────────────────────────────────────

@dataclass
class BacktestResult(ToDictMixin):
    """
    백테스트 종합 결과.
    프론트엔드 퍼포먼스 페이지에서 사용합니다.
    """
    start_date: date
    end_date: date
    initial_capital: float
    final_capital: float

    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0

    total_return_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0

    trades: List[Trade] = field(default_factory=list)

    @property
    def win_rate(self) -> float:
        """승률 (%). 거래 없으면 0"""
        if self.total_trades == 0:
            return 0.0
        return self.winning_trades / self.total_trades * 100

    @property
    def profit_factor(self) -> float:
        """
        Profit Factor = 총 이익 / 총 손실의 절댓값.
        1 이상이면 수익 전략, 높을수록 좋습니다.
        """
        gross_profit = sum(t.pnl for t in self.trades if t.pnl > 0)
        gross_loss = abs(sum(t.pnl for t in self.trades if t.pnl < 0))
        if gross_loss == 0:
            return float("inf")
        return gross_profit / gross_loss

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        # 계산 프로퍼티 추가
        d["win_rate"] = round(self.win_rate, 2)
        d["profit_factor"] = round(self.profit_factor, 4) if self.profit_factor != float("inf") else 999
        return d


# ─────────────────────────────────────────
# 시장 상태
# ─────────────────────────────────────────

@dataclass
class MarketStatus(ToDictMixin):
    """
    시장 전체 상태 요약.
    Market Gate API 응답(/api/kr/market-status)에서 반환됩니다.
    """
    gate: str                       # GREEN | YELLOW | RED
    score: int                      # 0~100점
    regime: str                     # bull | neutral | bear
    reasons: List[str] = field(default_factory=list)   # 판단 근거 요약
    metrics: Dict[str, float] = field(default_factory=dict)  # 세부 지표값
    updated_at: Optional[datetime] = None

    @property
    def is_tradable(self) -> bool:
        """GREEN 또는 YELLOW 시만 매매 허용"""
        return self.gate in ("GREEN", "YELLOW")
