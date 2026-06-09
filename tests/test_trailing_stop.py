"""engine/trailing_stop.py 유닛 테스트."""

from __future__ import annotations

import math

import pytest

from engine.trailing_stop import (
    TrailingState,
    compute_atr,
    initial_trailing_stop,
    should_exit,
    update_trailing_stop,
)


class TestComputeAtr:
    def test_short_series_returns_zeros(self):
        # 시리즈가 너무 짧으면 0 리스트
        assert compute_atr([100], [99], [99.5]) == [0.0]

    def test_period_smaller_than_n_uses_seed(self):
        highs = [10, 11, 12, 13, 14]
        lows = [9, 10, 11, 12, 13]
        closes = [9.5, 10.5, 11.5, 12.5, 13.5]
        atr = compute_atr(highs, lows, closes, period=3)
        # 기간 < n 이면 EMA 갱신, 시드 = 평균 TR
        assert len(atr) == 5
        assert all(v > 0 for v in atr)

    def test_constant_prices_atr_zero_after_seed(self):
        highs = [100] * 30
        lows = [100] * 30
        closes = [100] * 30
        atr = compute_atr(highs, lows, closes, period=14)
        # 모두 동일하면 TR=0 → ATR 도 0
        assert atr[-1] == 0.0

    def test_increasing_prices_positive_atr(self):
        highs = list(range(100, 130))
        lows = list(range(99, 129))
        closes = list(range(99, 129))
        atr = compute_atr(highs, lows, closes, period=14)
        assert atr[-1] > 0


class TestInitialTrailingStop:
    def test_basic_calculation(self):
        # entry=100, atr=2, k=1.5 → stop=100 - 3 = 97
        assert initial_trailing_stop(100, 2.0, 1.5) == 97.0

    def test_zero_floor(self):
        # 음수 stop 은 0 으로 floor
        assert initial_trailing_stop(10, 100.0, 1.5) == 0.0

    def test_default_k(self):
        # 기본 k=1.5
        assert initial_trailing_stop(100, 4.0) == 94.0


class TestUpdateTrailingStop:
    def test_peak_increases(self):
        # min_hold_days(2) 경과 후: peak 상승 → trailing stop 추종 (기본 k=2.0)
        state = TrailingState(
            entry_price=100, peak_price=100, atr_value=2.0,
            trailing_stop=97.0, days_held=2,
        )
        new = update_trailing_stop(state, today_high=105, today_close=104, today_atr=2.0)
        assert new.peak_price == 105
        assert new.trailing_stop == 101.0  # 105 - 2.0*2 = 101 (k=2.0, S1 완화)
        assert new.days_held == 3

    def test_day1_protection_holds_stop(self):
        # days_held < min_hold_days(2): peak 가 올라도 trailing 갱신 보류 (Day-1 흔들기 방지).
        # 9fb1fbf(Sprint 1)에서 추가된 보호 로직 — peak 만 추적하고 stop 은 진입 stop 유지.
        state = TrailingState(
            entry_price=100, peak_price=100, atr_value=2.0,
            trailing_stop=97.0, days_held=0,
        )
        new = update_trailing_stop(state, today_high=105, today_close=104, today_atr=2.0)
        assert new.peak_price == 105       # peak 는 추적
        assert new.trailing_stop == 97.0   # stop 은 보류 (Day-1 보호)
        assert new.days_held == 1

    def test_stop_monotonic_non_decreasing(self):
        # peak 가 떨어져도 trailing_stop 은 단조 비감소
        state = TrailingState(
            entry_price=100, peak_price=120, atr_value=2.0,
            trailing_stop=117.0, days_held=3,
        )
        new = update_trailing_stop(state, today_high=110, today_close=110, today_atr=2.0)
        assert new.peak_price == 120  # 기존 peak 유지
        # candidate = 120 - 2.0*2 = 116 < 117 → 단조성으로 기존 117 유지
        assert new.trailing_stop == 117.0

    def test_stop_rises_with_new_peak(self):
        state = TrailingState(
            entry_price=100, peak_price=110, atr_value=2.0,
            trailing_stop=107.0, days_held=2,
        )
        new = update_trailing_stop(state, today_high=120, today_close=119, today_atr=3.0)
        # peak=120, candidate=120 - 2.0*3=114.0, max(107, 114)=114.0 (k=2.0)
        assert new.trailing_stop == 114.0
        assert new.atr_value == 3.0


class TestShouldExit:
    def test_stop_loss_triggered(self):
        state = TrailingState(
            entry_price=100, peak_price=110, atr_value=2.0,
            trailing_stop=105.0, days_held=2,
        )
        # low=104 < stop=105 → stop_loss
        out = should_exit(state, today_low=104, today_close=106, max_hold_days=5)
        assert out == (True, "stop_loss", 105.0)

    def test_time_exit_triggered(self):
        state = TrailingState(
            entry_price=100, peak_price=110, atr_value=2.0,
            trailing_stop=105.0, days_held=5,
        )
        # 보유 5일 ≥ max_hold_days=5 → time_exit
        out = should_exit(state, today_low=108, today_close=109, max_hold_days=5)
        assert out == (True, "time_exit", 109)

    def test_no_exit(self):
        state = TrailingState(
            entry_price=100, peak_price=110, atr_value=2.0,
            trailing_stop=105.0, days_held=2,
        )
        out = should_exit(state, today_low=108, today_close=109, max_hold_days=5)
        assert out == (False, "", 0.0)

    def test_stop_priority_over_time(self):
        # stop_loss 와 time_exit 동시 조건 → stop_loss 우선
        state = TrailingState(
            entry_price=100, peak_price=110, atr_value=2.0,
            trailing_stop=108.0, days_held=5,
        )
        out = should_exit(state, today_low=107, today_close=108, max_hold_days=5)
        assert out[0] is True
        assert out[1] == "stop_loss"
