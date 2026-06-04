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
SIGNAL_LOG_CLOSE_PATH = ROOT / "data" / "signals_log_A_close.csv"
SIGNAL_LOG_NEXT_OPEN_PATH = ROOT / "data" / "signals_log_B_next_open.csv"

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
    "status",           # pending | entered | exited | invalidated
    "exit_date",
    "exit_price",
    "exit_reason",      # stop_loss | trailing_stop | time_exit | partial_stop | partial_time | manual | gap_skip
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


def _load(path: Path = SIGNAL_LOG_PATH) -> pd.DataFrame:
    """CSV 파일을 로드. 신규 컬럼이 빠진 구버전 CSV 는 자동 backfill."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        return pd.DataFrame(columns=COLUMNS)
    df = pd.read_csv(path, dtype={"ticker": str})
    # ATR 트레일링 + partial_exit 컬럼이 없으면 추가 (이전 버전 호환)
    for col in (
        "atr_value", "peak_price", "trailing_stop", "days_held",
        "partial_taken", "partial_return",
    ):
        if col not in df.columns:
            df[col] = pd.NA
    # 문자열 컬럼이 NaN-only 일 때 float64 로 추정되는 문제 방지
    # (이후 string 대입 시 FutureWarning → 미래 에러)
    for col in ("exit_date", "exit_reason"):
        if col in df.columns:
            df[col] = df[col].astype(object)
    return df


def _save(df: pd.DataFrame, path: Path = SIGNAL_LOG_PATH) -> None:
    """DataFrame을 CSV로 저장합니다."""
    df.to_csv(path, index=False, encoding="utf-8-sig")


def save_signal(signal_dict: dict, log_path: Path = SIGNAL_LOG_PATH) -> bool:
    """
    새 시그널을 CSV에 저장합니다.

    Args:
        signal_dict: engine.models.Signal.to_dict() 결과

    Returns:
        True (저장 성공), False (중복 또는 오류)
    """
    try:
        df = _load(log_path)

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

        new_row = pd.DataFrame([row])
        if df.empty:
            df = new_row
        else:
            df = pd.concat([df, new_row], ignore_index=True)
        _save(df, log_path)
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
    log_path: Path = SIGNAL_LOG_PATH,
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
        df = _load(log_path)
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

        _save(df, log_path)
        logger.info(f"[signal_tracker] 청산 기록: {ticker} {exit_reason} ({return_pct:+.1f}%)")
        return True

    except Exception as e:
        logger.error(f"[signal_tracker] update_exit 오류: {e}")
        return False


def get_open_signals(log_path: Path = SIGNAL_LOG_PATH) -> pd.DataFrame:
    """미청산(pending 또는 entered) 시그널 목록을 반환합니다."""
    df = _load(log_path)
    if df.empty:
        return df
    return df[df["status"].isin(["pending", "entered"])].copy()


def get_today_signals(log_path: Path = SIGNAL_LOG_PATH) -> pd.DataFrame:
    """당일 생성된 시그널 목록을 반환합니다."""
    df = _load(log_path)
    if df.empty:
        return df
    today = date.today().isoformat()
    return df[df["signal_date"] == today].copy()


def persist_screener_result(result, log_path: Path = SIGNAL_LOG_PATH) -> int:
    """ScreenerResult 의 모든 Signal 을 signals_log.csv 에 저장.

    중복(같은 ticker+signal_date)은 save_signal 이 알아서 skip.
    Returns: 새로 저장된 행 수.
    """
    saved = 0
    for sig in getattr(result, "signals", []):
        try:
            d = sig.to_dict()
        except AttributeError:
            d = dict(sig)
        if save_signal(d, log_path):
            saved += 1
    return saved


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
    atr_multiplier: float = 2.0,
    trailing_min_hold_days: int = 2,
    max_hold_days: int = 5,
    partial_exit_enabled: bool = True,
    partial_exit_target_pct: float = 8.0,
    partial_exit_ratio: float = 0.5,
    entry_timing: str = "close",
    max_gap_pct: float = 1.0,
    hard_stop_floor_pct: float = 8.0,
    rsi_overbought_exit_enabled: bool = False,
    rsi_overbought_threshold: float = 90.0,
    sanghan_exit_enabled: bool = True,
    sanghan_threshold_pct: float = 28.0,
    log_path: Path = SIGNAL_LOG_PATH,
) -> None:
    """
    미청산 시그널을 ATR 기반 트레일링 스톱으로 자동 추적.

    백테(`scripts/backtest_jongga.py`) 검증:
      - sw_pe_t8 (close 진입): WR 55.9%, EV +1.656%, MDD -53.32%, Sharpe 2.83
      - sw_nopen_gap1 (next_open + 갭 1%): WR 49.5%, EV +2.367%, MDD -48.02%

    Args:
        entry_timing              : "close" → 신호일 종가 진입 (기본)
                                    "next_open" → 다음 거래일 시가 진입 (갭 필터 적용)
        max_gap_pct               : next_open 모드에서 시가 갭이 +X% 초과면 status=invalidated
        hard_stop_floor_pct       : 진입가 대비 절대 하한 손절 % (O'Neil 규칙, 0이면 비활성)
        rsi_overbought_exit_enabled: RSI(2) 과열 시 당일 종가 청산 (Connors RSI, 기본 비활성)
        rsi_overbought_threshold  : RSI(2) 과열 판정 기준 (기본 90.0)
        sanghan_exit_enabled      : 상한가(+sanghan_threshold_pct%) 당일 50% 부분 익절
        sanghan_threshold_pct     : 상한가 판정 기준 등락률 % (기본 28%)

    exit_reason 코드:
        stop_loss      : ATR trailing stop 터치
        trailing_stop  : ATR trailing stop 터치 (track_signals 내부 표기 통일)
        time_exit      : max_hold_days 보유일 초과
        partial_stop   : 분할 익절 후 trailing stop 청산
        partial_time   : 분할 익절 후 time_exit 청산
        hard_stop      : 절대 하한 손절 (-hard_stop_floor_pct%)
        rsi_overbought : RSI(2) 과열 청산
        gap_skip       : next_open 갭 초과 무효화
        manual         : 수동 청산

    매일 장 마감 후 1회 호출:
      1) pending 시그널 → next_open 진입/갭 필터 처리
      2) 보유 종목의 OHLC + ATR 갱신
      3) peak_price / trailing_stop 단조 증가 갱신
      4) hard_stop_floor 터치 → hard_stop 청산 (ATR 이전 우선)
      5) 상한가 감지 → sanghan 50% 부분 익절 마킹
      6) RSI(2) > threshold → rsi_overbought 청산
      7) low ≤ trailing_stop → trailing_stop 청산
      8) days_held ≥ max_hold_days → time_exit
    """
    import pykrx.stock as pk_stock

    from engine.trailing_stop import (
        compute_atr,
        initial_trailing_stop,
        should_exit,
        update_trailing_stop,
        TrailingState,
    )

    df = _load(log_path)
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

            # ── next_open 진입 + 갭 필터 처리 ──
            # status=="pending" 이고 entry_timing=="next_open" 이면
            # signal_date 다음 거래일 시가 갭 검증 후 진입/무효화 결정.
            if entry_timing == "next_open" and str(row.get("status")) == "pending":
                sig_date_str = str(row.get("signal_date", ""))
                try:
                    sig_date_dt = pd.to_datetime(sig_date_str).date()
                except Exception:
                    sig_date_dt = None

                sig_idx = None
                if sig_date_dt is not None:
                    for i, dt in enumerate(ohlc.index):
                        if dt.date() == sig_date_dt:
                            sig_idx = i
                            break

                # 다음 거래일 OHLC 가 아직 없으면 대기 (다음 호출에서 처리)
                if sig_idx is None or sig_idx + 1 >= len(ohlc):
                    continue

                sig_close = float(ohlc.iloc[sig_idx]["종가"])
                next_open_px = float(ohlc.iloc[sig_idx + 1]["시가"])
                gap_pct = (next_open_px / sig_close - 1.0) * 100 if sig_close > 0 else 0.0

                if gap_pct > max_gap_pct:
                    df.at[idx, "status"] = "invalidated"
                    df.at[idx, "exit_date"] = ohlc.index[sig_idx + 1].date().isoformat()
                    df.at[idx, "exit_reason"] = "gap_skip"
                    df.at[idx, "exit_price"] = next_open_px
                    df.at[idx, "return_pct"] = 0.0
                    df.at[idx, "pnl"] = 0.0
                    logger.info(
                        f"[signal_tracker] 갭 무효화: {ticker} "
                        f"gap={gap_pct:+.2f}% > {max_gap_pct}% (skip)"
                    )
                    continue

                # 진입: entry_price 를 시가로 갱신, status=entered
                df.at[idx, "entry_price"] = next_open_px
                df.at[idx, "status"] = "entered"
                logger.info(
                    f"[signal_tracker] next_open 진입: {ticker} "
                    f"close={sig_close:.0f} → open={next_open_px:.0f} "
                    f"(gap={gap_pct:+.2f}%)"
                )
                try:
                    import paper_trading as _pt
                    from utils import notifier as _ntf
                    _qty = _safe_int(row.get("quantity"))
                    if _qty > 0 and next_open_px > 0:
                        _res = _pt.enter_position(
                            ticker=ticker,
                            name=str(row.get("name", ticker)),
                            entry_price=next_open_px,
                            quantity=_qty,
                            stop_price=_safe_float(row.get("stop_price")),
                            target_price=_safe_float(row.get("target_price")),
                            grade=str(row.get("grade", "")),
                            strategy="B_next_open",
                            signal_id=str(row.get("signal_id", "")),
                            signal_date=str(row.get("signal_date", "")),
                        )
                        if _res.get("ok"):
                            _ntf.notify_paper_entry(
                                ticker=ticker,
                                name=str(row.get("name", ticker)),
                                entry_price=next_open_px,
                                quantity=_qty,
                                invested=_res["position"]["invested"],
                                grade=str(row.get("grade", "")),
                                strategy="B_next_open",
                                cash_after=_res["cash_after"],
                            )
                except Exception as _pe:
                    logger.warning(f"[signal_tracker] paper B진입 오류 ({ticker}): {_pe}")
                # 진입 당일은 trailing 평가 skip (다음 호출부터 본격 trailing)
                if sig_idx + 1 == len(ohlc) - 1:
                    continue
                # ohlc 마지막이 진입일보다 더 이후면 그 시점부터 trailing 평가
                row = df.loc[idx]

            # ── close 진입: 처음 처리 시 pending → entered 전환 ──────────
            if entry_timing == "close" and str(row.get("status")) == "pending":
                df.at[idx, "status"] = "entered"
                row = df.loc[idx]
                try:
                    import paper_trading as _pt
                    from utils import notifier as _ntf
                    _qty = _safe_int(row.get("quantity"))
                    _ep  = _safe_float(row.get("entry_price"))
                    if _qty > 0 and _ep > 0:
                        _res = _pt.enter_position(
                            ticker=ticker,
                            name=str(row.get("name", ticker)),
                            entry_price=_ep,
                            quantity=_qty,
                            stop_price=_safe_float(row.get("stop_price")),
                            target_price=_safe_float(row.get("target_price")),
                            grade=str(row.get("grade", "")),
                            strategy="A_close",
                            signal_id=str(row.get("signal_id", "")),
                            signal_date=str(row.get("signal_date", "")),
                        )
                        if _res.get("ok"):
                            _ntf.notify_paper_entry(
                                ticker=ticker,
                                name=str(row.get("name", ticker)),
                                entry_price=_ep,
                                quantity=_qty,
                                invested=_res["position"]["invested"],
                                grade=str(row.get("grade", "")),
                                strategy="A_close",
                                cash_after=_res["cash_after"],
                            )
                except Exception as _pe:
                    logger.warning(f"[signal_tracker] paper A진입 오류 ({ticker}): {_pe}")

            entry_price = _safe_float(row.get("entry_price"))
            prev_peak = _safe_float(row.get("peak_price")) or entry_price
            prev_stop = _safe_float(row.get("trailing_stop")) or initial_trailing_stop(
                entry_price, today_atr, atr_multiplier
            )
            prev_days = _safe_int(row.get("days_held"))
            prev_atr = _safe_float(row.get("atr_value")) or today_atr
            prev_partial_taken = bool(_safe_int(row.get("partial_taken")))
            prev_partial_return = _safe_float(row.get("partial_return"))

            # ── 하드 플로어 스탑: 진입가 대비 -hard_stop_floor_pct% 절대 하한 (O'Neil 규칙) ──
            if hard_stop_floor_pct > 0 and entry_price > 0:
                hard_floor = entry_price * (1 - hard_stop_floor_pct / 100)
                if today_low <= hard_floor:
                    df.at[idx, "status"] = "exited"
                    df.at[idx, "exit_date"] = today.isoformat()
                    df.at[idx, "exit_price"] = hard_floor
                    df.at[idx, "exit_reason"] = "hard_stop"
                    return_pct = (hard_floor - entry_price) / entry_price * 100
                    df.at[idx, "return_pct"] = round(return_pct, 2)
                    df.at[idx, "pnl"] = round(
                        entry_price * _safe_int(row.get("quantity")) * return_pct / 100, 0
                    )
                    logger.info(
                        f"[signal_tracker] 하드 스탑 청산: {ticker} "
                        f"{return_pct:+.2f}% (hard floor -{hard_stop_floor_pct}%)"
                    )
                    try:
                        import paper_trading as _pt
                        from utils import notifier as _ntf
                        _r = _pt.exit_position(ticker=ticker, exit_price=hard_floor,
                                               exit_reason="hard_stop",
                                               exit_date=today.isoformat())
                        if _r.get("ok"):
                            _ntf.notify_paper_exit(
                                ticker=ticker, name=str(row.get("name", ticker)),
                                exit_price=hard_floor, pnl=_r["trade"]["pnl"],
                                return_pct=_r["trade"]["return_pct"],
                                exit_reason="hard_stop", cash_after=_r["cash_after"],
                            )
                    except Exception as _pe:
                        logger.warning(f"[signal_tracker] paper hard_stop 청산 오류 ({ticker}): {_pe}")
                    continue

            # ── 상한가 감지: +sanghan_threshold_pct%+ 상승 시 당일 50% 부분 익절 마킹 (한국장 특화) ──
            if (
                sanghan_exit_enabled
                and entry_price > 0
                and today_high >= entry_price * (1 + sanghan_threshold_pct / 100)
                and not prev_partial_taken
            ):
                sanghan_exit_price = today_high * 0.97  # 실제 체결은 종가 근처 가정 (보수적)
                partial_pct = (sanghan_exit_price - entry_price) / entry_price * 100
                prev_partial_taken = True
                prev_partial_return = partial_pct
                _update_trailing_fields(idx, df, partial_taken=1, partial_return=round(partial_pct, 2))
                logger.info(
                    f"[signal_tracker] 상한가 부분 익절: {ticker} "
                    f"+{partial_pct:.2f}% (잔량 trailing 유지)"
                )

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
                min_hold_days=trailing_min_hold_days,
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

            # ── RSI(2) 과열 청산 (Connors RSI: RSI(2) > threshold) ──
            if rsi_overbought_exit_enabled and len(closes) >= 3:
                gains = [max(closes[i] - closes[i - 1], 0) for i in range(-2, 0)]
                losses = [max(closes[i - 1] - closes[i], 0) for i in range(-2, 0)]
                avg_gain = sum(gains) / 2
                avg_loss = sum(losses) / 2
                if avg_loss > 0:
                    rsi2 = 100 - 100 / (1 + avg_gain / avg_loss)
                    if rsi2 > rsi_overbought_threshold:
                        remainder_pct = (today_close - entry_price) / entry_price * 100 if entry_price else 0.0
                        if state.partial_taken:
                            final_pct = (
                                partial_exit_ratio * prev_partial_return
                                + (1 - partial_exit_ratio) * remainder_pct
                            )
                        else:
                            final_pct = remainder_pct
                        df.at[idx, "status"] = "exited"
                        df.at[idx, "exit_date"] = today.isoformat()
                        df.at[idx, "exit_price"] = today_close
                        df.at[idx, "exit_reason"] = "rsi_overbought"
                        df.at[idx, "return_pct"] = round(final_pct, 2)
                        df.at[idx, "pnl"] = round(
                            entry_price * _safe_int(row.get("quantity")) * final_pct / 100, 0
                        )
                        logger.info(
                            f"[signal_tracker] RSI(2) 과열 청산: {ticker} "
                            f"RSI={rsi2:.1f} > {rsi_overbought_threshold} → {final_pct:+.2f}%"
                        )
                        try:
                            import paper_trading as _pt
                            from utils import notifier as _ntf
                            _r = _pt.exit_position(ticker=ticker, exit_price=today_close,
                                                   exit_reason="rsi_overbought",
                                                   exit_date=today.isoformat())
                            if _r.get("ok"):
                                _ntf.notify_paper_exit(
                                    ticker=ticker, name=str(row.get("name", ticker)),
                                    exit_price=today_close, pnl=_r["trade"]["pnl"],
                                    return_pct=_r["trade"]["return_pct"],
                                    exit_reason="rsi_overbought", cash_after=_r["cash_after"],
                                )
                        except Exception as _pe:
                            logger.warning(f"[signal_tracker] paper rsi_overbought 청산 오류 ({ticker}): {_pe}")
                        continue

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
                try:
                    import paper_trading as _pt
                    from utils import notifier as _ntf
                    _r = _pt.exit_position(ticker=ticker, exit_price=exit_price,
                                           exit_reason=reason_label,
                                           exit_date=today.isoformat())
                    if _r.get("ok"):
                        _ntf.notify_paper_exit(
                            ticker=ticker, name=str(row.get("name", ticker)),
                            exit_price=exit_price, pnl=_r["trade"]["pnl"],
                            return_pct=_r["trade"]["return_pct"],
                            exit_reason=reason_label, cash_after=_r["cash_after"],
                        )
                except Exception as _pe:
                    logger.warning(f"[signal_tracker] paper 청산 오류 ({ticker}): {_pe}")
            else:
                logger.debug(
                    f"[signal_tracker] {ticker} 추적: "
                    f"peak={state.peak_price:.0f} stop={state.trailing_stop:.0f} "
                    f"days={state.days_held}"
                )

        except Exception as e:
            logger.warning(f"[signal_tracker] {ticker} 추적 오류: {e}")

    _save(df, log_path)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    track_signals()
