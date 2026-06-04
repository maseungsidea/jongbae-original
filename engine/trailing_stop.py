"""
ATR 기반 트레일링 스톱 매니저 (engine/trailing_stop.py)

백테 결과(`scripts/backtest_jongga.py`)에서 검증된 사실:
  - 고정 +5% 익절은 EV 의 가장 큰 누수원이었다.
  - target=off + atr15(=ATR×1.5) 트레일링이 EV 4배.

운영 코드는 종가 1회 호출이 표준이므로 매일 1회 high/low/close 로
새 trailing stop 값을 재계산하면 충분하다. (인트라데이 추적은 차후)

Public API:
  - compute_atr(highs, lows, closes, period=14) → ATR 시리즈
  - update_trailing_stop(...) → 새 stop, peak_price
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence


def compute_atr(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 14,
) -> List[float]:
    """Wilder's ATR. 처음 period개는 단순평균 시드, 이후 EMA 갱신."""
    n = len(closes)
    if n < 2 or len(highs) != n or len(lows) != n:
        return [0.0] * n

    trs: List[float] = [highs[0] - lows[0]]
    for i in range(1, n):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)

    atr: List[float] = [0.0] * n
    if n <= period:
        avg = sum(trs) / n
        return [avg] * n

    seed = sum(trs[1 : period + 1]) / period
    atr[period] = seed
    for i in range(period + 1, n):
        atr[i] = (atr[i - 1] * (period - 1) + trs[i]) / period
    for i in range(period):
        atr[i] = seed
    return atr


@dataclass
class TrailingState:
    """포지션별 트레일링 상태."""

    entry_price: float
    peak_price: float       # 보유기간 최고가
    atr_value: float        # 최근 ATR
    trailing_stop: float    # 현재 stop 가격
    days_held: int = 0
    partial_taken: bool = False


def initial_trailing_stop(entry_price: float, atr_value: float, k: float = 1.5) -> float:
    """진입 직후 stop = entry - k×ATR."""
    return max(0.0, entry_price - k * atr_value)


def update_trailing_stop(
    state: TrailingState,
    today_high: float,
    today_close: float,
    today_atr: float,
    k: float = 2.0,
    min_hold_days: int = 2,
) -> TrailingState:
    """
    매 종가 마감 후 호출. peak_price 와 trailing_stop 을 갱신해 반환.

    - peak_price 는 today_high 까지만 따라간다 (재진입 X)
    - trailing_stop 은 max(기존, peak - k×ATR) 로 단조 증가
    - days_held < min_hold_days 인 동안은 trailing 갱신을 보류 (초기 흔들기 방지)
    - days_held += 1
    """
    new_peak = max(state.peak_price, today_high)

    # Day-1 보호: min_hold_days 미만이면 trailing 갱신 없이 기존 stop 유지
    if state.days_held < min_hold_days:
        new_stop = state.trailing_stop
    else:
        candidate = new_peak - k * today_atr
        new_stop = max(state.trailing_stop, candidate)

    return TrailingState(
        entry_price=state.entry_price,
        peak_price=new_peak,
        atr_value=today_atr,
        trailing_stop=new_stop,
        days_held=state.days_held + 1,
        partial_taken=state.partial_taken,
    )


def should_exit(
    state: TrailingState,
    today_low: float,
    today_close: float,
    max_hold_days: int = 5,
) -> tuple[bool, str, float]:
    """
    stop_loss / time_exit 판정.

    Returns:
        (exit_yn, reason, exit_price)
        reason ∈ {"stop_loss", "time_exit", ""}
    """
    if today_low <= state.trailing_stop:
        return True, "stop_loss", state.trailing_stop
    if state.days_held >= max_hold_days:
        return True, "time_exit", today_close
    return False, "", 0.0
