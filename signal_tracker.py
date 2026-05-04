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
    "exit_reason",      # stop_loss | take_profit | time_exit | manual
    "return_pct",
    "pnl",
    "created_at",
]


def _load() -> pd.DataFrame:
    """CSV 파일을 로드합니다. 파일이 없으면 빈 DataFrame을 반환합니다."""
    SIGNAL_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not SIGNAL_LOG_PATH.exists():
        return pd.DataFrame(columns=COLUMNS)
    return pd.read_csv(SIGNAL_LOG_PATH, dtype={"ticker": str})


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


def track_signals() -> None:
    """
    미청산 시그널을 현재 주가와 비교하여 손절/익절 자동 업데이트.
    scheduler.py에서 장 종료 후 호출됩니다.
    """
    import pykrx.stock as pk_stock  # noqa: F401

    open_signals = get_open_signals()
    if open_signals.empty:
        logger.info("[signal_tracker] 미청산 시그널 없음")
        return

    today_str = date.today().strftime("%Y%m%d")
    for _, row in open_signals.iterrows():
        ticker = str(row["ticker"])
        try:
            df_today = pk_stock.get_market_ohlcv_by_date(today_str, today_str, ticker)
            if df_today is None or df_today.empty:
                continue

            close_price = float(df_today.iloc[-1]["종가"])
            stop_price = float(row["stop_price"])
            target_price = float(row["target_price"])

            if close_price <= stop_price:
                update_exit(ticker, row["signal_date"], close_price, "stop_loss")
            elif close_price >= target_price:
                update_exit(ticker, row["signal_date"], close_price, "take_profit")

        except Exception as e:
            logger.warning(f"[signal_tracker] {ticker} 추적 오류: {e}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    track_signals()
