"""
엔진 전용 데이터 모델 (engine/models.py)

종가베팅 시그널 생성 엔진 내부에서 사용하는 데이터 클래스를 정의합니다.
- StockData: KRX에서 수집한 종목 실시간 데이터
- NewsItem: 뉴스 기사 단건
- SupplyData: 외인/기관 수급 집계
- ChartData: 일봉 OHLCV 단건
- ScoreDetail: 12점 채점 항목별 세부 점수
- ChecklistDetail: 주요 조건 충족 여부 체크리스트
- SignalStatus: 시그널 생명주기 상태
- Signal: 엔진이 생성하는 완전한 시그널 (채점 세부 포함)
- ScreenerResult: 스크리너 실행 결과 컨테이너
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional


# ─────────────────────────────────────────
# 수집 데이터 모델
# ─────────────────────────────────────────

@dataclass
class StockData:
    """
    KRX/yfinance에서 수집한 종목 실시간 데이터.

    KRXCollector.get_top_gainers() 와 get_stock_detail() 의 반환 타입입니다.
    """
    code: str           # 6자리 종목코드
    name: str
    market: str         # KOSPI | KOSDAQ
    sector: str
    close: float        # 현재가 (당일 종가 또는 실시간가)
    change_pct: float   # 등락률 (%)
    trading_value: int  # 거래대금 (원)
    volume: int         # 거래량 (주)
    marcap: int         # 시가총액 (원)
    high_52w: Optional[float] = None    # 52주 최고가 (없으면 None)
    low_52w: Optional[float] = None     # 52주 최저가


@dataclass
class NewsItem:
    """
    뉴스 기사 단건.
    EnhancedNewsCollector.get_stock_news() 의 반환 타입입니다.
    """
    title: str
    summary: str
    source: str
    url: str
    published_at: Optional[datetime] = None


@dataclass
class SupplyData:
    """
    외인/기관 수급 집계 (5일 누적).
    KRXCollector.get_supply_data() 의 반환 타입입니다.
    """
    foreign_buy_5d: int = 0     # 외인 5일 누적 순매수 (주)
    inst_buy_5d: int = 0        # 기관 5일 누적 순매수 (주)

    @property
    def is_both_positive(self) -> bool:
        """외인·기관 모두 순매수이면 True"""
        return self.foreign_buy_5d > 0 and self.inst_buy_5d > 0

    @property
    def is_either_positive(self) -> bool:
        """외인 또는 기관 중 하나라도 순매수이면 True"""
        return self.foreign_buy_5d > 0 or self.inst_buy_5d > 0


@dataclass
class ChartData:
    """
    일봉 OHLCV 단건.
    KRXCollector.get_chart_data() 가 반환하는 리스트의 원소입니다.
    """
    date: str           # "YYYY-MM-DD" 형식
    open: float
    high: float
    low: float
    close: float
    volume: int

    @property
    def body_ratio(self) -> float:
        """
        캔들 몸통 비율 = |close - open| / (high - low).
        장대양봉 판별에 사용합니다.
        """
        if self.high == self.low:
            return 0.0
        return abs(self.close - self.open) / (self.high - self.low)

    @property
    def upper_wick_ratio(self) -> float:
        """
        윗꼬리 비율 = (high - max(open, close)) / (high - low).
        윗꼬리가 짧을수록 강한 매수세를 의미합니다.
        """
        if self.high == self.low:
            return 0.0
        upper_wick = self.high - max(self.open, self.close)
        return upper_wick / (self.high - self.low)

    @property
    def is_bullish(self) -> bool:
        """양봉(종가 > 시가) 여부"""
        return self.close > self.open


# ─────────────────────────────────────────
# 채점 모델
# ─────────────────────────────────────────

@dataclass
class ScoreDetail:
    """
    12점 만점 채점 항목별 세부 점수.
    Scorer.calculate() 의 반환 타입 중 하나입니다.

    항목별 배점:
    - news         : 0~3 (뉴스/재료, LLM 기반)
    - volume       : 0~3 (거래대금)
    - chart        : 0~2 (차트패턴: 신고가, 이평선 정배열)
    - candle        : 0~1 (캔들형태: 장대양봉, 윗꼬리 짧음)
    - consolidation : 0~1 (기간조정: 횡보 후 돌파, 볼린저 수축)
    - supply        : 0~2 (수급: 외인+기관 순매수)
    """
    news: int = 0
    volume: int = 0
    chart: int = 0
    candle: int = 0
    consolidation: int = 0
    supply: int = 0
    llm_reason: str = ""        # LLM이 생성한 뉴스 분석 요약

    @property
    def total(self) -> int:
        """항목별 점수 합계 (최대 12점)"""
        return self.news + self.volume + self.chart + self.candle + self.consolidation + self.supply

    def to_dict(self) -> Dict[str, Any]:
        return {
            "news": self.news,
            "volume": self.volume,
            "chart": self.chart,
            "candle": self.candle,
            "consolidation": self.consolidation,
            "supply": self.supply,
            "total": self.total,
            "llm_reason": self.llm_reason,
        }


@dataclass
class ChecklistDetail:
    """
    주요 조건 충족 여부 체크리스트.
    Scorer.calculate() 와 함께 반환되며, 프론트엔드 카드 UI에 표시됩니다.
    """
    has_news: bool = False                          # 관련 뉴스 존재 여부
    news_sources: List[str] = field(default_factory=list)   # 뉴스 출처 목록
    is_new_high: bool = False                       # 52주 신고가 여부
    is_breakout: bool = False                       # 저항선 돌파 여부
    supply_positive: bool = False                   # 수급 긍정적 여부 (외인 or 기관)
    supply_both_positive: bool = False              # 외인+기관 동시 순매수 여부
    volume_surge: bool = False                      # 거래량 폭발 여부
    ma_aligned: bool = False                        # 이평선 정배열 여부
    long_candle: bool = False                       # 장대양봉 여부
    consolidation_done: bool = False                # 횡보 후 돌파 여부

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ─────────────────────────────────────────
# 시그널 모델
# ─────────────────────────────────────────

class SignalStatus(Enum):
    """
    시그널 생명주기 상태.
    - PENDING: 생성됐으나 아직 진입 전
    - ENTERED: 진입 완료
    - EXITED: 청산 완료
    """
    PENDING = "pending"
    ENTERED = "entered"
    EXITED = "exited"


@dataclass
class Signal:
    """
    엔진이 생성하는 완전한 종가베팅 시그널.

    루트 models.Signal 과 달리 채점 세부(ScoreDetail),
    체크리스트(ChecklistDetail), 뉴스 목록을 모두 포함합니다.
    API 응답 시에는 to_dict()로 직렬화하거나 루트 models.Signal로 변환합니다.
    """
    # ── 종목 식별 ──────────────────────────────
    stock_code: str
    stock_name: str
    market: str
    sector: str

    # ── 날짜/시간 ─────────────────────────────
    signal_date: date
    signal_time: datetime

    # ── 등급·점수 ─────────────────────────────
    grade: Any          # engine.config.Grade (순환 임포트 방지를 위해 Any)
    score: ScoreDetail
    checklist: ChecklistDetail

    # ── 뉴스 ──────────────────────────────────
    news_items: List[Dict]   # NewsItem.to_dict() 결과 목록

    # ── 가격·포지션 ───────────────────────────
    current_price: float
    entry_price: float
    stop_price: float
    target_price: float
    r_value: float          # 1R 금액 (손실 허용액)
    position_size: float    # 투자 금액 (원)
    quantity: int           # 매수 수량 (주)
    r_multiplier: float     # 등급별 R 배수

    # ── 참고 지표 ─────────────────────────────
    trading_value: int
    change_pct: float

    # ── 상태 ──────────────────────────────────
    status: SignalStatus = SignalStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """API 응답용 직렬화. 엔진 내부 객체를 JSON 호환 dict로 변환합니다."""
        return {
            "stock_code": self.stock_code,
            "stock_name": self.stock_name,
            "market": self.market,
            "sector": self.sector,
            "signal_date": self.signal_date.isoformat(),
            "signal_time": self.signal_time.isoformat(),
            "grade": self.grade.value if hasattr(self.grade, "value") else str(self.grade),
            "score": self.score.to_dict(),
            "checklist": self.checklist.to_dict(),
            "news_items": self.news_items,
            "current_price": self.current_price,
            "entry_price": self.entry_price,
            "stop_price": round(self.stop_price, 0),
            "target_price": round(self.target_price, 0),
            "r_value": self.r_value,
            "position_size": self.position_size,
            "quantity": self.quantity,
            "r_multiplier": self.r_multiplier,
            "trading_value": self.trading_value,
            "change_pct": self.change_pct,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
        }


# ─────────────────────────────────────────
# 스크리너 결과
# ─────────────────────────────────────────

@dataclass
class ScreenerResult:
    """
    스크리너 실행 결과 컨테이너.
    SignalGenerator.generate() 의 상위 레벨 반환 타입입니다.
    """
    date: date
    total_candidates: int           # 1차 필터 통과 종목 수
    filtered_count: int             # 채점 후 등급 B 이상 종목 수
    signals: List[Signal]           # 최종 시그널 목록

    by_grade: Dict[str, int] = field(default_factory=dict)    # 등급별 종목 수
    by_market: Dict[str, int] = field(default_factory=dict)   # 시장별 종목 수
    processing_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "date": self.date.isoformat(),
            "total_candidates": self.total_candidates,
            "filtered_count": self.filtered_count,
            "signals": [s.to_dict() for s in self.signals],
            "by_grade": self.by_grade,
            "by_market": self.by_market,
            "processing_time_ms": round(self.processing_time_ms, 2),
        }
