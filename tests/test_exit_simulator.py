"""
exit_simulator fidelity 계약 테스트 (tests/test_exit_simulator.py)

목적: engine/exit_simulator.simulate_exit 가 라이브 청산 로직(signal_tracker.track_signals)
의 분기를 정확히 재현하는지 잠근다. 향후 SoT 변경 시 silent drift 를 회귀로 잡는다.

라이브 평가 순서(고정):
  1) hard_stop floor (Day-0 포함 상시)  →  2) sanghan partial 마킹
  3) update_trailing_stop (Day-1 보호)   →  4) partial_exit(+8%) 마킹
  4.5) RSI(2) 과열 청산                   →  5) should_exit (trailing / time)
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.exit_simulator import ExitParams, simulate_exit


def _history(n=16, close=1000.0, half_range=10.0):
    """평탄한 히스토리 n개. TR=high-low=2*half_range 로 ATR 예측가능."""
    highs = [close + half_range] * n
    lows = [close - half_range] * n
    closes = [close] * n
    return highs, lows, closes


def _params(**kw):
    base = dict(
        atr_period=14, atr_multiplier=2.0, trailing_min_hold_days=2,
        max_hold_days=5, partial_exit_enabled=True, partial_exit_target_pct=8.0,
        partial_exit_ratio=0.5, hard_stop_floor_pct=8.0,
        sanghan_exit_enabled=True, sanghan_threshold_pct=28.0,
        rsi_overbought_exit_enabled=False, rsi_overbought_threshold=90.0,
    )
    base.update(kw)
    return ExitParams(**base)


def test_hard_stop_floor_fires_first():
    """진입 후 -8% floor 터치 → hard_stop, 정확히 -8% (Day-0 포함)."""
    h, l, c = _history()
    entry_idx = len(c) - 1  # 15
    entry = c[entry_idx]    # 1000
    # 첫 미래 바: low 가 hard floor(920) 아래
    h += [1005.0]
    l += [915.0]
    c += [950.0]
    res = simulate_exit(entry, h, l, c, entry_idx, _params())
    assert res.exit_reason == "hard_stop"
    assert res.return_pct == pytest.approx(-8.0, abs=1e-6)
    assert res.bars_held == 1


def test_time_exit_when_flat():
    """변동 없이 보유만기 도달 → time_exit (5영업일)."""
    h, l, c = _history()
    entry_idx = len(c) - 1
    entry = c[entry_idx]
    # 6개의 잔잔한 상승 바 (stop/target/floor 미접촉)
    for _ in range(6):
        h.append(1008.0)
        l.append(996.0)
        c.append(1004.0)
    res = simulate_exit(entry, h, l, c, entry_idx, _params())
    assert res.exit_reason == "time_exit"
    assert res.days_held >= 5
    assert res.return_pct == pytest.approx((1004 - 1000) / 1000 * 100, abs=0.5)


def test_partial_then_trailing_stop_weighted():
    """+8% partial 익절 마킹 후 trailing stop hit → partial_stop, 가중평균 수익."""
    h, l, c = _history()
    entry_idx = len(c) - 1
    entry = c[entry_idx]
    # bar1: +8% 돌파(high>=1080) → partial 마킹
    h.append(1090.0); l.append(1000.0); c.append(1085.0)
    # bar2: Day-1 보호 풀린 뒤 급락하여 trailing stop hit (단 hard floor 920 보다는 위)
    h.append(1085.0); l.append(1030.0); c.append(1035.0)
    # bar3: 더 떨어져 확실히 trailing 청산
    h.append(1060.0); l.append(1000.0); c.append(1010.0)
    res = simulate_exit(entry, h, l, c, entry_idx, _params())
    assert res.exit_reason in ("partial_stop", "partial_time")
    assert res.partial_taken is True
    # 가중평균: 0.5*8% + 0.5*(잔량) → 잔량이 양수이므로 2~8% 사이
    assert 1.0 < res.return_pct < 8.0


def test_initial_trailing_stop_active_on_day1():
    """Day-1 보호는 '래칫 보류'일 뿐 — 초기 trailing stop(entry-2×ATR≈-4%)은 첫날부터 활성.

    라이브 should_exit 는 days_held 게이팅이 없어 진입 첫 바라도 low<=trailing_stop 이면
    청산한다. ATR=20, k=2 → 초기 stop=960(-4%). hard floor(920,-8%)보다 위이므로
    -4% trailing 이 먼저 발동한다. (즉 진입 첫날 하방 = -4%, hard -8% 아님)
    """
    h, l, c = _history()
    entry_idx = len(c) - 1
    entry = c[entry_idx]
    # 첫 바: low 가 초기 trailing stop(960) 아래, 단 hard floor(920) 위
    h.append(1002.0); l.append(945.0); c.append(950.0)
    res = simulate_exit(entry, h, l, c, entry_idx, _params())
    assert res.exit_reason == "trailing_stop"
    assert res.return_pct == pytest.approx(-4.0, abs=1e-6)
    assert res.bars_held == 1


def test_day1_no_ratchet_tightening():
    """Day-1 보호의 실제 효과: 첫 2일은 stop 이 래칫업(타이트닝)되지 않는다.

    진입 첫날 high 가 크게 치솟아도 stop 은 초기값(960)에 동결되어야 한다.
    동결이 없었다면 stop 이 peak-2×ATR 로 올라가 같은 바 저점에 청산됐을 것.
    """
    h, l, c = _history()
    entry_idx = len(c) - 1
    entry = c[entry_idx]
    # day0: high 상승(1070, +8% partial 미달) → 래칫 없으면 stop≈1030 상향. low=1000<1030
    #       이라 래칫됐다면 청산됐을 것. 보호로 stop=960 동결 → low 1000>960, 미청산.
    h.append(1070.0); l.append(1000.0); c.append(1050.0)
    # day1: 동일 (여전히 days_held<2 동결)
    h.append(1070.0); l.append(1000.0); c.append(1050.0)
    # day2~: 고가 유지하여 trailing 미접촉 → 만기 청산 유도
    for _ in range(5):
        h.append(1055.0); l.append(1045.0); c.append(1050.0)
    res = simulate_exit(entry, h, l, c, entry_idx, _params())
    # 핵심 불변식: stop 기반 청산이 일어났다면 반드시 day1 이후(bars_held>2)여야 한다.
    assert res.exit_reason not in ("trailing_stop", "hard_stop") or res.bars_held > 2


def test_close_eval_entry_bar_hard_stop_d0():
    """close 전략(eval_entry_bar=True): 진입 바 자체의 low 가 floor 아래면 진입일(d0) hard_stop.

    라이브 close 는 진입 당일 호출에서 `continue` 없이 청산 블록으로 fall-through 하여
    진입 바 high/low 를 평가한다(signal_tracker.py:439~485). next_open(기본 skip)과의 비대칭.
    """
    h, l, c = _history()
    entry_idx = len(c) - 1
    entry = c[entry_idx]
    # 진입 바 자체를 floor 깨는 바로 교체 (low<=920)
    h[entry_idx] = 1010.0
    l[entry_idx] = 910.0
    c[entry_idx] = entry  # 진입가는 종가 유지
    res = simulate_exit(entry, h, l, c, entry_idx, _params(), eval_entry_bar=True)
    assert res.exit_reason == "hard_stop"
    assert res.bars_held == 0
    assert res.return_pct == pytest.approx(-8.0, abs=1e-6)


def test_close_skip_entry_bar_does_not_exit_d0():
    """eval_entry_bar=False 면 진입 바를 평가하지 않아 같은 d0 floor breach 를 무시."""
    h, l, c = _history()
    entry_idx = len(c) - 1
    entry = c[entry_idx]
    h[entry_idx] = 1010.0
    l[entry_idx] = 910.0  # 진입 바 floor breach
    c[entry_idx] = entry
    # 이후 바들은 평온
    for _ in range(6):
        h.append(1005.0); l.append(995.0); c.append(1000.0)
    res = simulate_exit(entry, h, l, c, entry_idx, _params(), eval_entry_bar=False)
    # 진입 바(d0) 의 hard floor breach 가 무시되어 hard_stop 이 아니어야 함
    assert res.bars_held >= 1
    assert not (res.exit_reason == "hard_stop" and res.bars_held == 0)


def test_rsi_overbought_exit_when_enabled():
    """RSI(2) 과열 청산: 플래그 on + 급등 후 미세 하락 → rsi_overbought."""
    h, l, c = _history()
    entry_idx = len(c) - 1
    entry = c[entry_idx]
    # bar1: +5% 상승(단 +8% partial 미달, high<1080)
    h.append(1055.0); l.append(1000.0); c.append(1050.0)
    # bar2: 미세 하락 → RSI(2) 과열 트리거 (avg_loss>0 보장)
    h.append(1052.0); l.append(1040.0); c.append(1049.0)
    res = simulate_exit(entry, h, l, c, entry_idx,
                        _params(rsi_overbought_exit_enabled=True, rsi_overbought_threshold=50.0))
    assert res.exit_reason in ("rsi_overbought", "partial_rsi")
    assert res.return_pct > 0


def test_rsi_disabled_by_default_does_not_fire():
    """플래그 off(기본) 면 RSI 과열이어도 청산하지 않음 (현재 운영 설정 = 영향 없음)."""
    h, l, c = _history()
    entry_idx = len(c) - 1
    entry = c[entry_idx]
    h.append(1055.0); l.append(1000.0); c.append(1050.0)
    h.append(1052.0); l.append(1040.0); c.append(1049.0)
    for _ in range(5):
        h.append(1052.0); l.append(1045.0); c.append(1050.0)
    res = simulate_exit(entry, h, l, c, entry_idx, _params())  # rsi off
    assert res.exit_reason != "rsi_overbought"
    assert res.exit_reason != "partial_rsi"
