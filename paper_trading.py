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


# ── 계좌 정합화 (reconcile) ───────────────────────────────────
# paper_account 은 전략 A(close) 단독 구동 (CLAUDE.md: 전략 A = primary 당일 종가 진입).
# 전략 B(next_open)는 별도 CSV 로 비교/백테용으로만 추적, 페이퍼 계좌 미구동.
# legacy signals_log.csv 는 분석·백테용 원장이라 paper_account 와 동기화 대상 아님.
PAPER_SOURCE_PATH = ROOT / "data" / "signals_log_A_close.csv"


def _read_signal_rows(path: Path) -> list[dict]:
    """전략 신호 CSV(기본 A_close)를 dict 리스트로 로드 (BOM 안전, csv 표준 모듈)."""
    import csv
    if not path.exists():
        return []
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def reconcile_account(signal_log_path: Optional[Path] = None) -> dict:
    """signals_log.csv(SoT)로부터 paper_account.json 을 결정론적으로 재구성.

    배경: paper_account.json 과 signals_log.csv 는 별도 원장이라
    CSV 가 백테/수동/재실행으로 직접 갱신되면 두 원장이 drift 한다.
    (예: 청산이 CSV 에만 기록되고 paper_account 에 포지션이 잔류)

    해법: CSV 를 단일 진실원장(SoT)으로 삼아 paper_account 를 재구성.
    enter_position 의 "동일 티커 중복 보유 금지" 가드를 시간순 구간 겹침으로 재현.
    track_signals() 종료 시 매 사이클 호출 → 자가 치유.

    분할익절(partial_exit) 주의: CSV pnl 은 가중평균(0.5×partial + 0.5×remainder)을
    반영한 값이고, 라이브 exit_position 은 전량을 최종가로 계산하는 잠정값이다.
    reconcile 는 CSV pnl 을 authoritative 로 채택 → 매 사이클 종료 시 정합 복원.

    Returns:
        {"ok", "changed", "before": {...}, "after": {...}, "papered", "skipped"}
    """
    path = signal_log_path or PAPER_SOURCE_PATH
    rows = _read_signal_rows(path)

    # 진입 대상: entered/exited 만. 테스트 픽스처(name==TEST) 제외.
    cands = [
        r for r in rows
        if r.get("status") in ("entered", "exited") and r.get("name") != "TEST"
    ]
    cands.sort(key=lambda r: (r.get("signal_date", ""), r.get("created_at", "")))

    # 시간순 구간(interval) 겹침으로 중복 진입 스킵 재현
    held_intervals: dict = {}   # ticker -> [(entry_date, exit_date|None), ...]
    papered: list = []
    skipped: list = []
    for r in cands:
        tk = r["ticker"]
        ed = r.get("signal_date", "")
        xd = r.get("exit_date") if r.get("status") == "exited" else None
        xd = xd or None
        blocked = any(
            eA <= ed and (xA is None or xA >= ed)
            for (eA, xA) in held_intervals.get(tk, [])
        )
        if blocked:
            skipped.append(r)
        else:
            papered.append(r)
            held_intervals.setdefault(tk, []).append((ed, xd))

    # 계좌 재구성
    acc = load_account()
    seed = acc.get("seed", SEED_MONEY)
    positions: list = []
    trades: list = []
    realized_pnl = 0.0
    invested_open = 0.0

    for r in papered:
        qty = int(float(r.get("quantity") or 0))
        entry = float(r.get("entry_price") or 0)
        # 라이브 enter_position 가드(signal_tracker: _qty>0 and _ep>0)와 정합 — phantom 방지
        if qty <= 0 or entry <= 0:
            continue
        invested = round(entry * qty)
        common = {
            "id":           r.get("signal_id", "")[:8] or "unknown",
            "ticker":       r["ticker"],
            "name":         r.get("name", r["ticker"]),
            "grade":        r.get("grade", ""),
            "strategy":     "A_close",
            "entry_price":  entry,
            "quantity":     qty,
            "stop_price":   float(r.get("stop_price") or 0),
            "target_price": float(r.get("target_price") or 0),
            "invested":     invested,
            "entry_date":   r.get("signal_date", ""),
        }
        if r.get("status") == "exited":
            pnl = round(float(r.get("pnl") or 0))
            realized_pnl += pnl
            trades.append({
                **common,
                "exit_price":  float(r.get("exit_price") or 0),
                "pnl":         pnl,
                "return_pct":  round(float(r.get("return_pct") or 0), 2),
                "exit_date":   r.get("exit_date", ""),
                "exit_reason": r.get("exit_reason", ""),
            })
        else:  # entered (미청산)
            invested_open += invested
            positions.append({**common, "status": "entered"})

    new_cash = round(seed + realized_pnl - invested_open)

    before = {"cash": acc.get("cash"), "open": len(acc.get("positions", [])),
              "trades": len(acc.get("trades", []))}
    after = {"cash": new_cash, "open": len(positions), "trades": len(trades)}
    changed = before != after

    acc["cash"] = new_cash
    acc["positions"] = positions
    acc["trades"] = trades
    _save_account(acc)

    if changed:
        logger.info(
            f"[paper] reconcile: drift 수정 | "
            f"현금 {before['cash']:,}→{after['cash']:,}원, "
            f"보유 {before['open']}→{after['open']}건, "
            f"청산 {before['trades']}→{after['trades']}건 "
            f"(papered {len(papered)} / skipped {len(skipped)})"
        )
    else:
        logger.debug(f"[paper] reconcile: 정합 상태 (변경 없음)")

    return {
        "ok": True, "changed": changed, "before": before, "after": after,
        "papered": len(papered), "skipped": len(skipped),
    }
