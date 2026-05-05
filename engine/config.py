"""
엔진 전용 설정 모듈 (engine/config.py)

종가베팅 신호 생성 엔진에서 사용하는 Enum/Dataclass 설정을 정의합니다.
- Grade: 신호 등급 (S/A/B/C)
- GradeConfig: 등급별 최소 점수·거래대금 기준
- SignalConfig: 12점 채점 시스템의 모든 파라미터 통합 관리
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List


# ─────────────────────────────────────────
# Enum 정의
# ─────────────────────────────────────────

class Grade(Enum):
    """
    종가베팅 신호 등급.

    S: 최고 확신 (10점+, 거래대금 1조+)
    A: 고확신 (8점+, 거래대금 5천억+)
    B: 보통 (6점+, 거래대금 1천억+)
    C: 미달 (필터링 대상)
    """
    S = "S"
    A = "A"
    B = "B"
    C = "C"  # 제외 대상


# ─────────────────────────────────────────
# Dataclass 정의
# ─────────────────────────────────────────

@dataclass
class GradeConfig:
    """
    등급별 최소 점수·거래대금 기준.

    Scorer.determine_grade() 에서 이 설정을 참조합니다.
    """
    min_score: int              # 최소 총점 (12점 만점 기준)
    min_trading_value: int      # 최소 거래대금 (원)
    r_multiplier: float         # 이 등급의 R 배수 (PositionSizer에서 참조)


@dataclass
class SignalConfig:
    """
    종가베팅 시그널 생성 전체 파라미터.

    ─ 기본 필터 ───────────────────────────────
    min_trading_value  : 최소 거래대금 (50억 원, 스크리닝 1차 필터)
    max_change_pct     : 당일 급등 제외 상한선 (+15%)
    min_close_price    : 동전주 제외 최소 종가 (1,000원)

    ─ 제외 조건 ───────────────────────────────
    excluded_keywords  : 뉴스 제목에 포함 시 제외할 키워드
    excluded_sectors   : 분석 제외 업종

    ─ 점수 가중치 (12점 만점) ──────────────────
    뉴스/재료 0~3점, 거래대금 0~3점, 차트패턴 0~2점,
    캔들형태 0~1점, 기간조정 0~1점, 수급 0~2점

    ─ 등급별 기준 ─────────────────────────────
    grade_configs : Grade → GradeConfig 매핑

    ─ 매매 설정 ───────────────────────────────
    stop_loss_pct      : 손절 비율 (-3%)
    take_profit_pct    : 익절 비율 (+5%)
    r_ratio            : 계좌 대비 1R 비율 (0.5%)

    ─ 뉴스 키워드 ─────────────────────────────
    bullish_keywords   : 호재 키워드
    bearish_keywords   : 악재 키워드
    """

    # ── 기본 필터 ──────────────────────────────
    min_trading_value: int = 5_000_000_000      # 50억 원
    max_change_pct: float = 15.0                # 당일 +15% 이상 제외
    min_close_price: int = 1_000                # 1,000원 미만 동전주 제외
    top_n_per_market: int = 30                  # 시장별 상위 N개 종목 분석

    # ── 제외 조건 ──────────────────────────────
    excluded_keywords: List[str] = field(default_factory=lambda: [
        "관리종목", "상장폐지", "감사의견", "자본잠식",
        "횡령", "배임", "소송", "부도", "파산",
    ])
    excluded_sectors: List[str] = field(default_factory=lambda: [
        "스팩", "리츠", "ETF", "ETN",
    ])

    # ── 채점 세부 설정 ─────────────────────────
    # 거래대금 구간별 점수 (원, 점수)
    volume_score_tiers: List[tuple] = field(default_factory=lambda: [
        (1_000_000_000_000, 3),   # 1조 이상 → 3점
        (500_000_000_000, 2),     # 5천억 이상 → 2점
        (100_000_000_000, 1),     # 1천억 이상 → 1점
    ])

    # 차트 패턴 기준
    new_high_lookback: int = 52             # 52주 신고가 기준
    ma_alignment_days: List[int] = field(default_factory=lambda: [5, 20, 60])  # 이평선 정배열

    # 캔들 기준
    long_candle_body_ratio: float = 0.7     # 장대양봉: 몸통 비율 70% 이상
    small_upper_wick_ratio: float = 0.1     # 윗꼬리 짧음: 전체 대비 10% 이하

    # 기간 조정 (횡보) 기준
    consolidation_bb_squeeze_pct: float = 0.03  # 볼린저 밴드 폭 3% 이하

    # 수급 기준
    supply_lookback_days: int = 5           # 외인/기관 순매수 집계 기간

    # ── 등급별 기준 ────────────────────────────
    grade_configs: Dict[str, GradeConfig] = field(default_factory=lambda: {
        Grade.S.value: GradeConfig(min_score=10, min_trading_value=1_000_000_000_000, r_multiplier=3.0),
        Grade.A.value: GradeConfig(min_score=8,  min_trading_value=500_000_000_000,   r_multiplier=2.0),
        Grade.B.value: GradeConfig(min_score=6,  min_trading_value=100_000_000_000,   r_multiplier=1.5),
        Grade.C.value: GradeConfig(min_score=0,  min_trading_value=0,                 r_multiplier=0.0),
    })

    # ── 매매 설정 ──────────────────────────────
    # 손절/익절 (1차 백테에서 +5% 고정 익절은 EV 의 가장 큰 누수원으로 확인됨.
    # signal_tracker 가 ATR 트레일링을 별도 관리하므로 take_profit_pct 는
    # 정보용 ceiling 으로만 남기고 실제 청산은 trailing_stop / time_exit 으로.)
    stop_loss_pct: float = 3.0              # 진입 직후 1일차 백업 손절 -3%
    take_profit_pct: float = 20.0           # 정보용 (실 청산은 trailing 이 결정)
    r_ratio: float = 0.005                  # 1R = 계좌의 0.5%

    # ── ATR 트레일링 (signal_tracker.track_signals) ───────────────
    # 백테 검증 (sw_pe_t8): partial_exit + atr15 + fixed8 target + hold=5d
    # → WR 55.9%, EV +1.656%, RR 1.26, MDD -53.32%, Sharpe 2.83 (현 최적)
    atr_period: int = 14                     # ATR 계산 기간
    atr_multiplier: float = 1.5              # peak - k×ATR 의 k 값
    max_hold_days: int = 5                   # time_exit 발동 일수
    partial_exit_enabled: bool = True        # 50% 분할 익절 활성화
    partial_exit_target_pct: float = 8.0     # 분할 익절 발동 +8%
    partial_exit_ratio: float = 0.5          # 익절 비중 50%

    # ── LLM 설정 ──────────────────────────────
    llm_news_limit: int = 5                 # LLM에 전달할 최대 뉴스 개수
    llm_timeout_sec: int = 10              # LLM API 타임아웃

    # ── 뉴스 키워드 ────────────────────────────
    bullish_keywords: List[str] = field(default_factory=lambda: [
        "계약", "수주", "공급", "특허", "FDA", "임상",
        "신약", "흑자", "영업이익", "매출 증가", "수출",
        "자사주 매입", "배당", "호실적", "어닝 서프라이즈",
    ])
    bearish_keywords: List[str] = field(default_factory=lambda: [
        "손실", "적자", "영업손실", "소송", "리콜",
        "과징금", "벌금", "사기", "분식회계",
    ])

    def get_grade_config(self, grade: "Grade") -> GradeConfig:
        """등급에 해당하는 GradeConfig 반환"""
        return self.grade_configs[grade.value]
