"""
충실한 청산 시뮬레이터 (engine/exit_simulator.py)

목적: 백테스터가 **라이브 청산 로직과 동일한** 결과를 내도록, signal_tracker.track_signals
의 per-bar 청산 평가를 단일 함수로 추출/재현한다. 기존 backtest_jongga.py 의 static-stop
(stop=entry-k×ATR 1회 고정)은 라이브의 trailing 래칫·Day-1 보호·hard_stop·분할익절을
반영하지 못해 EV 측정이 부정확했다 (DESIGN-S2 근본원인).

라이브 primitive(engine.trailing_stop)를 그대로 재사용하므로 fidelity 가 보장된다.
track_signals 의 청산 평가 순서(signal_tracker.py 483~672)를 1:1 로 따른다:
    1) hard_stop floor (-hard_stop_floor_pct%, Day-0 포함 상시)
    2) 상한가(sanghan) 부분익절 마킹 (+sanghan_threshold_pct%)
    3) update_trailing_stop (peak·stop 갱신, Day-1 min_hold 보호)
    4) partial_exit (+partial_exit_target_pct% → 50% 익절 마킹)
    5) should_exit (trailing stop hit / time_exit)

향후: track_signals 가 이 모듈을 호출하도록 리팩토링하면 라이브-백테 완전 단일화 (DRY).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

from engine.trailing_stop import (
    TrailingState,
    compute_atr,
    initial_trailing_stop,
    should_exit,
    update_trailing_stop,
)


@dataclass
class ExitParams:
    """청산 시뮬 파라미터 (SignalConfig 의 청산 관련 필드 미러)."""
    atr_period: int = 14
    atr_multiplier: float = 2.0
    trailing_min_hold_days: int = 2
    max_hold_days: int = 5
    partial_exit_enabled: bool = True
    partial_exit_target_pct: float = 8.0
    partial_exit_ratio: float = 0.5
    hard_stop_floor_pct: float = 8.0
    sanghan_exit_enabled: bool = True
    sanghan_threshold_pct: float = 28.0
    rsi_overbought_exit_enabled: bool = False
    rsi_overbought_threshold: float = 90.0


@dataclass
class ExitResult:
    """단일 포지션 청산 결과."""
    exit_price: float
    exit_reason: str          # hard_stop | trailing_stop | partial_stop | time_exit | partial_time
    return_pct: float         # net 아님, gross 수익률 (분할 시 가중평균)
    days_held: int
    partial_taken: bool
    partial_return: float     # 분할 익절분 수익률 (gross)
    bars_held: int = 0        # 진입 바 대비 청산 바 오프셋 (exit_idx - entry_idx); exit_date 복원용


def simulate_exit(
    entry_price: float,
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    entry_idx: int,
    params: ExitParams,
    eval_entry_bar: bool = False,
) -> ExitResult:
    """
    진입 직후부터 청산까지 라이브 로직을 그대로 재생.

    Args:
        entry_price: 진입가 (close 전략=신호일 종가, next_open 전략=익일 시가)
        highs/lows/closes: 전체 OHLCV 시퀀스 (진입 전 히스토리 + 진입 후 미래 포함)
        entry_idx: entry_price 가 체결된 바의 인덱스
        params: 청산 파라미터
        eval_entry_bar: True 면 진입 바(entry_idx)부터 청산 평가 — 라이브 close 전략은
            진입 당일 호출에서 `continue` 없이 청산 블록으로 fall-through 하므로 진입 바
            자체(그 바의 high/low)를 평가한다(signal_tracker.py:439~485). False(기본)면
            진입 다음 바부터 — 라이브 next_open 은 진입 당일을 명시적으로 skip(:433).

    Returns:
        ExitResult. 미래 바가 없으면 마지막 종가로 time_exit 근사.
    """
    n = len(closes)
    atr_series = compute_atr(highs, lows, closes, params.atr_period)
    atr_at_entry = atr_series[entry_idx] if 0 <= entry_idx < n else 0.0

    state = TrailingState(
        entry_price=entry_price,
        peak_price=entry_price,
        atr_value=atr_at_entry,
        trailing_stop=initial_trailing_stop(entry_price, atr_at_entry, params.atr_multiplier),
        days_held=0,
        partial_taken=False,
    )
    partial_return = 0.0
    hard_floor = entry_price * (1 - params.hard_stop_floor_pct / 100) if params.hard_stop_floor_pct > 0 else 0.0

    # 평가 시작 바: close=진입 바부터(fall-through), next_open=진입 다음 바부터
    eval_start = entry_idx if eval_entry_bar else entry_idx + 1
    for i in range(eval_start, n):
        today_high, today_low, today_close = highs[i], lows[i], closes[i]
        today_atr = atr_series[i]

        # ── 1) hard_stop floor (Day-0 포함 상시) ──
        if hard_floor > 0 and today_low <= hard_floor:
            return ExitResult(
                exit_price=hard_floor, exit_reason="hard_stop",
                return_pct=(hard_floor - entry_price) / entry_price * 100,
                days_held=state.days_held, partial_taken=state.partial_taken,
                partial_return=partial_return, bars_held=i - entry_idx,
            )

        # ── 2) 상한가 부분익절 마킹 ──
        if (
            params.sanghan_exit_enabled and not state.partial_taken
            and today_high >= entry_price * (1 + params.sanghan_threshold_pct / 100)
        ):
            sanghan_px = today_high * 0.97
            partial_return = (sanghan_px - entry_price) / entry_price * 100
            state.partial_taken = True

        # ── 3) trailing 갱신 (Day-1 보호 내장) ──
        state = update_trailing_stop(
            state, today_high=today_high, today_close=today_close,
            today_atr=today_atr, k=params.atr_multiplier,
            min_hold_days=params.trailing_min_hold_days,
        )

        # ── 4) partial_exit (+target% → 50% 익절 마킹) ──
        if (
            params.partial_exit_enabled and not state.partial_taken
            and today_high >= entry_price * (1 + params.partial_exit_target_pct / 100)
        ):
            partial_return = params.partial_exit_target_pct
            state.partial_taken = True

        # ── 4.5) RSI(2) 과열 청산 (라이브 signal_tracker 580~625 미러) ──
        if params.rsi_overbought_exit_enabled and i >= 2:
            gains = [max(closes[j] - closes[j - 1], 0.0) for j in (i - 1, i)]
            losses = [max(closes[j - 1] - closes[j], 0.0) for j in (i - 1, i)]
            avg_gain = sum(gains) / 2
            avg_loss = sum(losses) / 2
            if avg_loss > 0:
                rsi2 = 100 - 100 / (1 + avg_gain / avg_loss)
                if rsi2 > params.rsi_overbought_threshold:
                    remainder_pct = (today_close - entry_price) / entry_price * 100
                    if state.partial_taken:
                        final_pct = (
                            params.partial_exit_ratio * partial_return
                            + (1 - params.partial_exit_ratio) * remainder_pct
                        )
                    else:
                        final_pct = remainder_pct
                    # 라이브(signal_tracker.py:600)는 partial 여부와 무관하게 항상 rsi_overbought
                    return ExitResult(
                        exit_price=today_close, exit_reason="rsi_overbought", return_pct=final_pct,
                        days_held=state.days_held, partial_taken=state.partial_taken,
                        partial_return=partial_return, bars_held=i - entry_idx,
                    )

        # ── 5) should_exit (trailing stop / time_exit) ──
        exit_yn, reason, exit_px = should_exit(
            state, today_low=today_low, today_close=today_close,
            max_hold_days=params.max_hold_days,
        )
        if exit_yn:
            base = "trailing_stop" if reason == "stop_loss" else reason
            remainder_pct = (exit_px - entry_price) / entry_price * 100
            if state.partial_taken:
                label = "partial_stop" if reason == "stop_loss" else "partial_time"
                final_pct = (
                    params.partial_exit_ratio * partial_return
                    + (1 - params.partial_exit_ratio) * remainder_pct
                )
            else:
                label = base
                final_pct = remainder_pct
            return ExitResult(
                exit_price=exit_px, exit_reason=label, return_pct=final_pct,
                days_held=state.days_held, partial_taken=state.partial_taken,
                partial_return=partial_return, bars_held=i - entry_idx,
            )

    # 미래 바 소진 → 마지막 종가로 청산 (time_exit 근사)
    last_close = closes[-1]
    remainder_pct = (last_close - entry_price) / entry_price * 100
    if state.partial_taken:
        final_pct = (
            params.partial_exit_ratio * partial_return
            + (1 - params.partial_exit_ratio) * remainder_pct
        )
        label = "partial_time"
    else:
        final_pct = remainder_pct
        label = "time_exit"
    return ExitResult(
        exit_price=last_close, exit_reason=label, return_pct=final_pct,
        days_held=state.days_held, partial_taken=state.partial_taken,
        partial_return=partial_return, bars_held=max(1, n - 1 - entry_idx),
    )
