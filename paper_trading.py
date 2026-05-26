"""
페이퍼 트레이딩 계좌 관리 (paper_trading.py)

씨드머니 1000만원으로 시작하는 가상 계좌.
시그널 진입/청산 시 잔고와 포지션을 자동으로 반영한다.

데이터 저장: data/paper_account.json
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
ACCOUNT_PATH = ROOT / "data" / "paper_account.json"

SEED_MONEY = 10_000_000  # 초기 씨드머니 1000만원


# ── 계좌 초기화 ──────────────────────────────────────────────
def _default_account() -> dict:
    return {
        "seed":       SEED_MONEY,
        "cash":       SEED_MONEY,
        "created_at": date.today().isoformat(),
        "positions":  [],   # 보유 중인 포지션
        "trades":     [],   # 청산된 거래 내역
    }


def load_account() -> dict:
    ACCOUNT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not ACCOUNT_PATH.exists():
        acc = _default_account()
        _save_account(acc)
        return acc
    with open(ACCOUNT_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save_account(acc: dict) -> None:
    ACCOUNT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(ACCOUNT_PATH, "w", encoding="utf-8") as f:
        json.dump(acc, f, ensure_ascii=False, indent=2)


# ── 포지션 진입 ──────────────────────────────────────────────
def enter_position(
    ticker: str,
    name: str,
    entry_price: float,
    quantity: int,
    stop_price: float,
    target_price: float,
    grade: str,
    strategy: str,
    signal_id: str = "",
    signal_date: str = "",
) -> dict:
    """
    포지션 진입 처리.

    Returns:
        {"ok": True/False, "position": {...}, "cash_after": int, "msg": str}
    """
    acc = load_account()
    invested = entry_price * quantity

    if acc["cash"] < invested:
        msg = f"잔고 부족: 필요 {invested:,.0f}원 / 가용 {acc['cash']:,.0f}원"
        logger.warning(f"[paper] 진입 실패 ({ticker}): {msg}")
        return {"ok": False, "msg": msg}

    # 이미 같은 종목 포지션이 있으면 중복 방지
    if any(p["ticker"] == ticker and p["status"] == "entered" for p in acc["positions"]):
        msg = f"이미 보유 중: {ticker}"
        logger.info(f"[paper] {msg}")
        return {"ok": False, "msg": msg}

    position = {
        "id":           signal_id or str(uuid.uuid4())[:8],
        "ticker":       ticker,
        "name":         name,
        "grade":        grade,
        "strategy":     strategy,
        "entry_price":  entry_price,
        "quantity":     quantity,
        "stop_price":   stop_price,
        "target_price": target_price,
        "invested":     round(invested),
        "entry_date":   signal_date or date.today().isoformat(),
        "status":       "entered",
    }

    acc["cash"] -= round(invested)
    acc["positions"].append(position)
    _save_account(acc)

    logger.info(
        f"[paper] 진입: {name}({ticker}) {quantity}주 @ {entry_price:,.0f}원 "
        f"= {invested/10000:.1f}만원 | 잔고 {acc['cash']/10000:.1f}만원"
    )
    return {"ok": True, "position": position, "cash_after": acc["cash"]}


# ── 포지션 청산 ──────────────────────────────────────────────
def exit_position(
    ticker: str,
    exit_price: float,
    exit_reason: str = "manual",
    exit_date: Optional[str] = None,
) -> dict:
    """
    포지션 청산 처리.

    Returns:
        {"ok": True/False, "trade": {...}, "cash_after": int, "msg": str}
    """
    acc = load_account()

    # 보유 포지션 찾기
    pos = next(
        (p for p in acc["positions"]
         if p["ticker"] == ticker and p["status"] == "entered"),
        None,
    )
    if pos is None:
        msg = f"보유 포지션 없음: {ticker}"
        logger.warning(f"[paper] 청산 실패: {msg}")
        return {"ok": False, "msg": msg}

    qty = pos["quantity"]
    entry_price = pos["entry_price"]
    proceeds = exit_price * qty
    pnl = (exit_price - entry_price) * qty
    return_pct = (exit_price - entry_price) / entry_price * 100

    trade = {
        "id":           pos["id"],
        "ticker":       pos["ticker"],
        "name":         pos["name"],
        "grade":        pos["grade"],
        "strategy":     pos["strategy"],
        "entry_price":  entry_price,
        "exit_price":   exit_price,
        "quantity":     qty,
        "invested":     pos["invested"],
        "pnl":          round(pnl),
        "return_pct":   round(return_pct, 2),
        "entry_date":   pos["entry_date"],
        "exit_date":    exit_date or date.today().isoformat(),
        "exit_reason":  exit_reason,
    }

    # 계좌 업데이트
    pos["status"] = "exited"
    acc["cash"] += round(proceeds)
    acc["trades"].append(trade)
    # positions 에서 청산된 항목 제거 (entered 상태만 유지)
    acc["positions"] = [p for p in acc["positions"] if p["status"] == "entered"]
    _save_account(acc)

    sign = "+" if pnl >= 0 else ""
    logger.info(
        f"[paper] 청산: {pos['name']}({ticker}) {exit_reason} "
        f"{sign}{return_pct:.1f}% (PnL {sign}{pnl/10000:.1f}만원) | "
        f"잔고 {acc['cash']/10000:.1f}만원"
    )
    return {"ok": True, "trade": trade, "cash_after": acc["cash"]}


# ── 계좌 요약 ────────────────────────────────────────────────
def get_summary(current_prices: Optional[dict] = None) -> dict:
    """
    계좌 현황 요약.

    Args:
        current_prices: {ticker: current_price} 현재가 dict (없으면 진입가 기준)

    Returns:
        {
          "seed": 10000000,
          "cash": 8500000,
          "positions_value": 1600000,   # 현재가 기준 포지션 평가액
          "total_value": 10100000,      # cash + positions_value
          "total_return_pct": 1.0,
          "total_pnl": 100000,
          "positions": [...],           # 보유 포지션 + 평가손익
          "trades": [...],              # 청산 내역 (최근 20건)
          "win_rate": 60.0,
          "trade_count": 5,
        }
    """
    acc = load_account()
    cp = current_prices or {}

    positions_with_pnl = []
    positions_value = 0
    for pos in acc["positions"]:
        ticker = pos["ticker"]
        cur_price = cp.get(ticker, pos["entry_price"])
        cur_val = cur_price * pos["quantity"]
        unrealized_pnl = (cur_price - pos["entry_price"]) * pos["quantity"]
        unrealized_pct = (cur_price - pos["entry_price"]) / pos["entry_price"] * 100
        positions_value += cur_val
        positions_with_pnl.append({
            **pos,
            "current_price":   cur_price,
            "current_value":   round(cur_val),
            "unrealized_pnl":  round(unrealized_pnl),
            "unrealized_pct":  round(unrealized_pct, 2),
        })

    total_value = acc["cash"] + positions_value
    total_pnl = total_value - acc["seed"]
    total_return_pct = total_pnl / acc["seed"] * 100

    # 승률 계산
    closed = acc["trades"]
    wins = [t for t in closed if t["pnl"] > 0]
    win_rate = len(wins) / len(closed) * 100 if closed else 0.0

    return {
        "seed":             acc["seed"],
        "cash":             acc["cash"],
        "positions_value":  round(positions_value),
        "total_value":      round(total_value),
        "total_pnl":        round(total_pnl),
        "total_return_pct": round(total_return_pct, 2),
        "positions":        positions_with_pnl,
        "trades":           list(reversed(closed))[:20],
        "win_rate":         round(win_rate, 1),
        "trade_count":      len(closed),
        "open_count":       len(positions_with_pnl),
    }


# ── 계좌 초기화 (관리자용) ─────────────────────────────────────
def reset_account() -> dict:
    """계좌를 씨드머니 상태로 초기화."""
    acc = _default_account()
    _save_account(acc)
    logger.info(f"[paper] 계좌 초기화: 씨드 {SEED_MONEY:,}원")
    return acc
