"""
VCP 시그널 추적 및 CSV 저장 모듈 (signal_tracker.py)

스크리너가 발생시킨 시그널을 data/signals_log.csv 에 기록하고
진입/청산 상태를 추적합니다.

책임:
- 새 시그널 저장 (save_signal)
- 청산 상태 업데이트 (update_exit)
- 미청산 시그널 조회 (get_open_signals)
- 당일 시그널 조회 (get_today_signals)
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
SIGNAL_LOG_PATH = ROOT / "data" / "signals_log.csv"

# CSV 컬럼 스키마
# v2: peak_price / atr_value / trailing_stop / days_held + partial_taken / partial_return 추가
COLUMNS = [
    "signal_id",       # UUID 또는 ticker+date 조합
    "ticker",
    "name",
    "market",
    "sector",
    "grade",
    "score",
    "signal_date",
    "entry_price",
    "stop_price",
    "target_price",
    "position_size",
    "quantity",
    "r_multiplier",
    "status",           # pending | entered | exited
    "exit_date",
    "exit_price",
    "exit_reason",      # stop_loss | trailing_stop | time_exit | partial_stop | partial_time | manual
    "return_pct",
    "pnl",
    "created_at",
    # ── ATR 트레일링 + partial_exit 추적 ──
    "atr_value",        # 최근 ATR(14)
    "peak_price",       # 보유 기간 최고가
    "trailing_stop",    # 현재 ATR 기반 동적 손절가
    "days_held",        # 보유 일수
    "partial_taken",    # 분할 익절 실행 여부 (0/1)
    "partial_return",   # 1차 분할 청산 시 수익률(%) — 최종 return_pct는 가중평균
]


def _load() -> pd.DataFrame:
    """CSV 파일을 로드. 신규 컬럼이 빠진 구버전 CSV 는 자동 backfill."""
    SIGNAL_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not SIGNAL_LOG_PATH.exists():
        return pd.DataFrame(columns=COLUMNS)
    df = pd.read_csv(SIGNAL_LOG_PATH, dtype={"ticker": str})
    # ATR 트레일링 + partial_exit 컬럼이 없으면 추가 (이전 버전 호환)
    for col in (
        "atr_value", "peak_price", "trailing_stop", "days_held",
        "partial_taken", "partial_return",
    ):
        if col not in df.columns:
            df[col] = pd.NA
    return df


def _save(df: pd.DataFrame) -> None:
    """DataFrame을 CSV로 저장합니다."""
    df.to_csv(SIGNAL_LOG_PATH, index=False, encoding="utf-8-sig")


def save_signal(signal_dict: dict) -> bool:
    """
    새 시그널을 CSV에 저장합니다.

    Args:
        signal_dict: engine.models.Signal.to_dict() 결과

    Returns:
        True (저장 성공), False (중복 또는 오류)
    """
    try:
        df = _load()

        # 중복 방지: 같은 종목+날짜 시그널은 1개만 허용
        ticker = signal_dict.get("stock_code", "")
        signal_date = signal_dict.get("signal_date", "")
        if not df.empty and ((df["ticker"] == ticker) & (df["signal_date"] == signal_date)).any():
            logger.debug(f"[signal_tracker] 중복 시그널 무시: {ticker} {signal_date}")
            return False

        import uuid
        row = {
            "signal_id": str(uuid.uuid4())[:8],
            "ticker": ticker,
            "name": signal_dict.get("stock_name", ""),
            "market": signal_dict.get("market", ""),
            "sector": signal_dict.get("sector", ""),
            "grade": signal_dict.get("grade", ""),
            "score": signal_dict.get("score", {}).get("total", 0),
            "signal_date": signal_date,
            "entry_price": signal_dict.get("entry_price", 0),
            "stop_price": signal_dict.get("stop_price", 0),
            "target_price": signal_dict.get("target_price", 0),
            "position_size": signal_dict.get("position_size", 0),
            "quantity": signal_dict.get("quantity", 0),
            "r_multiplier": signal_dict.get("r_multiplier", 0),
            "status": "pending",
            "exit_date": None,
            "exit_price": None,
            "exit_reason": "",
            "return_pct": None,
            "pnl": None,
            "created_at": signal_dict.get("created_at", ""),
        }

        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
        _save(df)
        logger.info(f"[signal_tracker] 저장: {ticker} {signal_date} ({row['grade']}등급)")
        return True

    except Exception as e:
        logger.error(f"[signal_tracker] save_signal 오류: {e}")
        return False


def update_exit(
    ticker: str,
    signal_date: str,
    exit_price: float,
    exit_reason: str = "manual",
    exit_date: Optional[str] = None,
) -> bool:
    """
    특정 시그널의 청산 정보를 업데이트합니다.

    Args:
        ticker: 종목코드
        signal_date: 시그널 날짜 (YYYY-MM-DD)
        exit_price: 청산가
        exit_reason: 청산 사유 (stop_loss / take_profit / time_exit / manual)
        exit_date: 청산일 (None이면 오늘)

    Returns:
        True (업데이트 성공), False (시그널 없음 또는 오류)
    """
    try:
        df = _load()
        mask = (df["ticker"] == ticker) & (df["signal_date"] == signal_date)
        if not mask.any():
            logger.warning(f"[signal_tracker] 시그널 없음: {ticker} {signal_date}")
            return False

        idx = df[mask].index[0]
        entry_price = float(df.at[idx, "entry_price"])
        quantity = int(df.at[idx, "quantity"])
        return_pct = (exit_price - entry_price) / entry_price * 100
        pnl = (exit_price - entry_price) * quantity

        df.at[idx, "status"] = "exited"
        df.at[idx, "exit_date"] = exit_date or date.today().isoformat()
        df.at[idx, "exit_price"] = exit_price
        df.at[idx, "exit_reason"] = exit_reason
        df.at[idx, "return_pct"] = round(return_pct, 2)
        df.at[idx, "pnl"] = round(pnl, 0)

        _save(df)
        logger.info(f"[signal_tracker] 청산 기록: {ticker} {exit_reason} ({return_pct:+.1f}%)")
        return True

    except Exception as e:
        logger.error(f"[signal_tracker] update_exit 오류: {e}")
        return False


def get_open_signals() -> pd.DataFrame:
    """미청산(pending 또는 entered) 시그널 목록을 반환합니다."""
    df = _load()
    if df.empty:
        return df
    return df[df["status"].isin(["pending", "entered"])].copy()


def get_today_signals() -> pd.DataFrame:
    """당일 생성된 시그널 목록을 반환합니다."""
    df = _load()
    if df.empty:
        return df
    today = date.today().isoformat()
    return df[df["signal_date"] == today].copy()


def _update_trailing_fields(idx: int, df: pd.DataFrame, **fields) -> None:
    """signals_log.csv 의 한 행에 ATR/peak/stop 등 컬럼을 안전하게 갱신."""
    for k, v in fields.items():
        if k in df.columns:
            df.at[idx, k] = v


def _safe_float(value, default: float = 0.0) -> float:
    """NaN / None / 빈 문자열을 default 로 변환."""
    try:
        f = float(value)
        return default if pd.isna(f) else f
    except (TypeError, ValueError):
        return default


def _safe_int(value, default: int = 0) -> int:
    """NaN / None / 빈 문자열을 default 로 변환."""
    try:
        f = float(value)
        return default if pd.isna(f) else int(f)
    except (TypeError, ValueError):
        return default


def track_signals(
    atr_period: int = 14,
    atr_multiplier: float = 1.5,
    max_hold_days: int = 5,
    partial_exit_enabled: bool = True,
    partial_exit_target_pct: float = 8.0,
    partial_exit_ratio: float = 0.5,
) -> None:
    """
    미청산 시그널을 ATR 기반 트레일링 스톱으로 자동 추적.

    백테(`scripts/backtest_jongga.py`) 검증:
      - target=off + atr15 + hold=5d 가 EV +1.602%, RR 1.61, 월 25건.
      - 고정 +5% 익절은 EV 의 가장 큰 누수원이라 제거함.

    매일 장 마감 후 1회 호출:
      1) 보유 종목의 OHLC + ATR 갱신
      2) peak_price / trailing_stop 단조 증가 갱신
      3) low ≤ trailing_stop → trailing_stop 청산
      4) days_held ≥ max_hold_days → time_exit
    """
    import pykrx.stock as pk_stock

    from engine.trailing_stop import (
        compute_atr,
        initial_trailing_stop,
        should_exit,
        update_trailing_stop,
        TrailingState,
    )

    df = _load()
    if df.empty:
        logger.info("[signal_tracker] 시그널 없음")
        return

    open_mask = df["status"].isin(["pending", "entered"])
    if not open_mask.any():
        logger.info("[signal_tracker] 미청산 시그널 없음")
        return

    today = date.today()
    today_str = today.strftime("%Y%m%d")
    # ATR 계산용으로 60일치 OHLC 확보
    from datetime import timedelta
    start_str = (today - timedelta(days=120)).strftime("%Y%m%d")

    for idx in df[open_mask].index:
        row = df.loc[idx]
        ticker = str(row["ticker"])
        try:
            ohlc = pk_stock.get_market_ohlcv_by_date(start_str, today_str, ticker)
            if ohlc is None or ohlc.empty:
                continue

            highs = ohlc["고가"].astype(float).tolist()
            lows = ohlc["저가"].astype(float).tolist()
            closes = ohlc["종가"].astype(float).tolist()

            atr_series = compute_atr(highs, lows, closes, period=atr_period)
            today_high, today_low, today_close = highs[-1], lows[-1], closes[-1]
            today_atr = atr_series[-1] if atr_series else 0.0

            entry_price = _safe_float(row.get("entry_price"))
            prev_peak = _safe_float(row.get("peak_price")) or entry_price
            prev_stop = _safe_float(row.get("trailing_stop")) or initial_trailing_stop(
                entry_price, today_atr, atr_multiplier
            )
            prev_days = _safe_int(row.get("days_held"))
            prev_atr = _safe_float(row.get("atr_value")) or today_atr
            prev_partial_taken = bool(_safe_int(row.get("partial_taken")))
            prev_partial_return = _safe_float(row.get("partial_return"))

            state = TrailingState(
                entry_price=entry_price,
                peak_price=prev_peak,
                atr_value=prev_atr,
                trailing_stop=prev_stop,
                days_held=prev_days,
                partial_taken=prev_partial_taken,
            )
            state = update_trailing_stop(
                state, today_high=today_high, today_close=today_close,
                today_atr=today_atr, k=atr_multiplier,
            )

            # ─ partial_exit 처리: 1차 +8% target 도달 시 50% 익절 ─
            partial_just_taken = False
            if (
                partial_exit_enabled
                and not state.partial_taken
                and entry_price > 0
                and today_high >= entry_price * (1 + partial_exit_target_pct / 100)
            ):
                partial_price = entry_price * (1 + partial_exit_target_pct / 100)
                partial_pct = (partial_price - entry_price) / entry_price * 100
                state.partial_taken = True
                prev_partial_return = partial_pct
                partial_just_taken = True
                logger.info(
                    f"[signal_tracker] 분할 익절: {ticker} +{partial_pct:.2f}% "
                    f"(잔량 50% trailing 유지)"
                )

            _update_trailing_fields(
                idx, df,
                atr_value=round(today_atr, 4),
                peak_price=round(state.peak_price, 0),
                trailing_stop=round(state.trailing_stop, 0),
                days_held=state.days_held,
                partial_taken=int(state.partial_taken),
                partial_return=round(prev_partial_return, 2) if state.partial_taken else None,
            )

            exit_yn, reason, exit_price = should_exit(
                state, today_low=today_low, today_close=today_close,
                max_hold_days=max_hold_days,
            )
            if exit_yn:
                # exit reason="stop_loss" 인 경우 정확한 의미는 trailing 이지만
                # 기존 분석 호환을 위해 trailing_stop 으로 명시
                base_reason = "trailing_stop" if reason == "stop_loss" else reason
                if state.partial_taken:
                    reason_label = "partial_stop" if reason == "stop_loss" else "partial_time"
                else:
                    reason_label = base_reason

                df.at[idx, "status"] = "exited"
                df.at[idx, "exit_date"] = today.isoformat()
                df.at[idx, "exit_price"] = exit_price
                df.at[idx, "exit_reason"] = reason_label

                remainder_pct = (exit_price - entry_price) / entry_price * 100 if entry_price else 0.0
                # partial_exit 시 가중평균: 50% × partial_return + 50% × remainder
                if state.partial_taken:
                    final_pct = (
                        partial_exit_ratio * prev_partial_return
                        + (1 - partial_exit_ratio) * remainder_pct
                    )
                else:
                    final_pct = remainder_pct

                qty = _safe_int(row.get("quantity"))
                df.at[idx, "return_pct"] = round(final_pct, 2)
                df.at[idx, "pnl"] = round(entry_price * qty * final_pct / 100, 0)
                logger.info(
                    f"[signal_tracker] 청산: {ticker} {reason_label} "
                    f"({final_pct:+.2f}%, hold={state.days_held}d, "
                    f"partial={state.partial_taken})"
                )
            else:
                logger.debug(
                    f"[signal_tracker] {ticker} 추적: "
                    f"peak={state.peak_price:.0f} stop={state.trailing_stop:.0f} "
                    f"days={state.days_held}"
                )

        except Exception as e:
            logger.warning(f"[signal_tracker] {ticker} 추적 오류: {e}")

    _save(df)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    track_signals()
