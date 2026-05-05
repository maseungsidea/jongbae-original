"""signal_tracker.py 통합 테스트."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

import signal_tracker


@pytest.fixture(autouse=True)
def cleanup_csv(tmp_path, monkeypatch):
    """각 테스트마다 임시 signals_log.csv 사용."""
    test_path = tmp_path / "signals_log.csv"
    monkeypatch.setattr(signal_tracker, "SIGNAL_LOG_PATH", test_path)
    yield
    if test_path.exists():
        test_path.unlink()


def make_signal_dict(ticker="005930", entry=70000, qty=100):
    return {
        "stock_code": ticker, "stock_name": "TEST", "market": "KOSPI", "sector": "",
        "grade": "A", "score": {"total": 9},
        "signal_date": "2026-05-05", "entry_price": entry,
        "stop_price": int(entry * 0.97), "target_price": int(entry * 1.05),
        "position_size": entry * qty, "quantity": qty,
        "r_multiplier": 2.0, "created_at": "2026-05-05",
    }


def make_ohlc(close_path: list[float], high_offset=500, low_offset=500):
    """가격 시계열로 OHLC DataFrame 생성."""
    n = len(close_path)
    return pd.DataFrame({
        "시가": close_path,
        "고가": [c + high_offset for c in close_path],
        "저가": [c - low_offset for c in close_path],
        "종가": close_path,
        "거래량": [1_000_000] * n,
    }, index=pd.date_range("2026-04-01", periods=n))


class TestSchemaCompat:
    def test_load_empty_returns_full_columns(self):
        df = signal_tracker._load()
        assert df.empty
        for col in (
            "atr_value", "peak_price", "trailing_stop", "days_held",
            "partial_taken", "partial_return",
        ):
            assert col in df.columns

    def test_load_legacy_csv_backfills_columns(self, tmp_path, monkeypatch):
        # ATR 컬럼 없는 구버전 CSV 만들고 _load 호출
        legacy = pd.DataFrame([{
            "signal_id": "abc", "ticker": "005930", "name": "TEST",
            "market": "KOSPI", "sector": "", "grade": "A", "score": 9,
            "signal_date": "2026-05-05", "entry_price": 70000,
            "stop_price": 67900, "target_price": 73500,
            "position_size": 7000000, "quantity": 100, "r_multiplier": 2.0,
            "status": "pending", "exit_date": None, "exit_price": None,
            "exit_reason": "", "return_pct": None, "pnl": None,
            "created_at": "2026-05-05",
        }])
        legacy_path = tmp_path / "signals_log.csv"
        legacy.to_csv(legacy_path, index=False)
        monkeypatch.setattr(signal_tracker, "SIGNAL_LOG_PATH", legacy_path)

        df = signal_tracker._load()
        for col in ("atr_value", "peak_price", "trailing_stop", "days_held"):
            assert col in df.columns


class TestSafeHelpers:
    def test_safe_float_handles_nan(self):
        assert signal_tracker._safe_float(float("nan")) == 0.0
        assert signal_tracker._safe_float(None) == 0.0
        assert signal_tracker._safe_float("") == 0.0
        assert signal_tracker._safe_float(123.45) == 123.45

    def test_safe_int_handles_nan(self):
        assert signal_tracker._safe_int(float("nan")) == 0
        assert signal_tracker._safe_int(None) == 0
        assert signal_tracker._safe_int(42.7) == 42


class TestSaveSignal:
    def test_save_creates_file_with_v2_columns(self):
        ok = signal_tracker.save_signal(make_signal_dict())
        assert ok is True
        df = signal_tracker._load()
        assert len(df) == 1
        assert df.iloc[0]["ticker"] == "005930"
        # 신규 컬럼은 NaN/None 으로 비어있음
        assert pd.isna(df.iloc[0]["peak_price"])

    def test_duplicate_save_returns_false(self):
        sig = make_signal_dict()
        signal_tracker.save_signal(sig)
        ok = signal_tracker.save_signal(sig)
        assert ok is False


class TestTrackSignals:
    def test_normal_run_updates_atr_columns(self):
        signal_tracker.save_signal(make_signal_dict())
        prices = list(np.linspace(68000, 71500, 30))
        with patch("pykrx.stock.get_market_ohlcv_by_date", return_value=make_ohlc(prices)):
            signal_tracker.track_signals(
                atr_period=14, atr_multiplier=1.5, max_hold_days=5,
                partial_exit_enabled=False,
            )

        df = signal_tracker._load()
        row = df.iloc[0]
        assert row.status == "pending"
        assert not pd.isna(row.atr_value)
        assert not pd.isna(row.peak_price)
        assert not pd.isna(row.trailing_stop)
        assert row.days_held == 1.0

    def test_crash_triggers_trailing_stop(self):
        signal_tracker.save_signal(make_signal_dict())
        # 29일간 70000 유지 후 마지막날 폭락 → low 가 stop 깨짐
        prices = [70000] * 29 + [42000]
        ohlc = make_ohlc(prices)
        # 마지막날 low 를 명시적으로 매우 낮게
        ohlc.iloc[-1, ohlc.columns.get_loc("저가")] = 40000
        with patch("pykrx.stock.get_market_ohlcv_by_date", return_value=ohlc):
            signal_tracker.track_signals(
                atr_period=14, atr_multiplier=1.5, max_hold_days=10,
                partial_exit_enabled=False,
            )

        df = signal_tracker._load()
        row = df.iloc[0]
        assert row.status == "exited"
        assert row.exit_reason == "trailing_stop"

    def test_partial_exit_then_stop_returns_weighted_avg(self):
        signal_tracker.save_signal(make_signal_dict(entry=70000))
        # +8% target = 75600 도달, 다음 날 폭락
        prices = [70000] * 29 + [76000]
        ohlc = make_ohlc(prices)
        ohlc.iloc[-1, ohlc.columns.get_loc("고가")] = 76300  # 75600 도달
        ohlc.iloc[-1, ohlc.columns.get_loc("저가")] = 75800
        with patch("pykrx.stock.get_market_ohlcv_by_date", return_value=ohlc):
            signal_tracker.track_signals(
                atr_period=14, atr_multiplier=1.5, max_hold_days=10,
                partial_exit_enabled=True,
                partial_exit_target_pct=8.0,
                partial_exit_ratio=0.5,
            )

        df = signal_tracker._load()
        row = df.iloc[0]
        # partial 익절 후 status 는 여전히 pending
        assert row.status == "pending"
        assert int(row.partial_taken) == 1
        assert abs(float(row.partial_return) - 8.0) < 0.001

        # 다음 날 폭락
        next_ohlc = pd.concat([ohlc, pd.DataFrame({
            "시가": [76000], "고가": [76500], "저가": [60000], "종가": [62000],
            "거래량": [1500000],
        }, index=pd.date_range("2026-05-01", periods=1))])

        with patch("pykrx.stock.get_market_ohlcv_by_date", return_value=next_ohlc):
            signal_tracker.track_signals(
                atr_period=14, atr_multiplier=1.5, max_hold_days=10,
                partial_exit_enabled=True,
                partial_exit_target_pct=8.0,
                partial_exit_ratio=0.5,
            )

        df = signal_tracker._load()
        row = df.iloc[0]
        assert row.status == "exited"
        assert row.exit_reason == "partial_stop"
        # return_pct = 0.5*8 + 0.5*remainder, 이때 remainder 는 trailing_stop 청산가 기준
        # remainder ≈ (stop - entry)/entry*100 인데 stop 은 ATR 기반이라 정확한 값보다는
        # final return_pct 가 4% 이상 (~5~7%) 사이로 나오는지 확인
        assert 4.0 <= float(row.return_pct) <= 8.0

    def test_no_open_signals_no_op(self):
        # 빈 CSV 에서 track_signals 호출 → 무사 리턴
        with patch("pykrx.stock.get_market_ohlcv_by_date") as m:
            signal_tracker.track_signals()
            m.assert_not_called()


class TestUpdateExit:
    def test_manual_update_exit(self):
        signal_tracker.save_signal(make_signal_dict(entry=70000, qty=100))
        ok = signal_tracker.update_exit(
            ticker="005930", signal_date="2026-05-05",
            exit_price=73500, exit_reason="manual",
        )
        assert ok is True
        df = signal_tracker._load()
        row = df.iloc[0]
        assert row.status == "exited"
        assert row.exit_reason == "manual"
        assert abs(float(row.return_pct) - 5.0) < 0.01
        assert int(row.pnl) == 350000  # (73500-70000) * 100

    def test_update_nonexistent_ticker_returns_false(self):
        ok = signal_tracker.update_exit("999999", "2026-05-05", 1000, "manual")
        assert ok is False
