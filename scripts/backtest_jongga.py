"""
종가베팅 historical backtester (scripts/backtest_jongga.py)

data/daily_prices.csv 를 가지고 engine/scorer 의 12점 채점을 매 거래일
재현하여 진입·청산을 시뮬레이션한다.

한계 (백테스트 가정):
- 뉴스 / LLM 점수 = 0 (과거 뉴스 수집 불가, 정보 누수 방지)
- 수급(외인·기관 5d) = 0 (per-day 수급 데이터 부재)
  → 12점 만점 중 7점이 cap. cutoff sweep 시 이 점 감안.
- 거래수수료 0.21% round-trip (한국 시장 표준)
- 한 종목당 sequential overlap (in_position 동안 새 진입 차단)

사용법:
    python scripts/backtest_jongga.py \
        --cutoff 5 --hold-days 5 --entry-timing close --trailing atr15 \
        --label baseline

출력:
    data/backtests/<label>.json   — trades + summary stats
    콘솔 metrics 요약
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.config import Grade, SignalConfig
from engine.models import ChartData, StockData
from engine.scorer import Scorer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

PRICES_PATH = ROOT / "data" / "daily_prices.csv"
OUT_DIR = ROOT / "data" / "backtests"
FEE_RT = 0.0021  # 한국 round-trip 수수료 + 세금


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--cutoff", type=int, default=5,
                   help="총점 cutoff (12점 만점, 백테스트는 7점 cap)")
    p.add_argument("--min-trading-value", type=int, default=10_000_000_000,
                   help="최소 거래대금 (원). default 100억")
    p.add_argument("--allow-grade", action="store_true",
                   help="determine_grade 통과 + cutoff (운영과 동일)")
    p.add_argument("--hold-days", type=int, default=5)
    p.add_argument("--entry-timing", choices=["close", "next_open"], default="close")
    p.add_argument("--trailing", choices=["off", "atr10", "atr15", "atr20", "fixed3"],
                   default="atr15", help="손절 룰. fixed3=고정 -3%")
    p.add_argument("--target", choices=["off", "fixed5", "fixed8", "fixed10"],
                   default="fixed5", help="익절. fixed5=+5%")
    p.add_argument("--start", default=None, help="백테스트 시작일 (YYYY-MM-DD)")
    p.add_argument("--end", default=None, help="백테스트 종료일")
    p.add_argument("--label", default="run", help="결과 파일 라벨")
    p.add_argument("--max-rows-debug", type=int, default=0,
                   help="디버그: ticker 수 제한 (0=전체)")
    return p.parse_args()


def compute_atr(window: pd.DataFrame, period: int = 14) -> float:
    """단순 ATR(14). window는 최소 period+1 행."""
    if len(window) < period + 1:
        return 0.0
    h = window["high"].values
    l = window["low"].values
    c = window["close"].values
    tr = np.maximum(h[1:] - l[1:],
                    np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
    return float(np.mean(tr[-period:]))


def make_charts(window: pd.DataFrame) -> list[ChartData]:
    """ pandas window를 ChartData list로 변환 """
    out = []
    for row in window.itertuples(index=False):
        out.append(ChartData(
            date=str(row.date), open=float(row.open), high=float(row.high),
            low=float(row.low), close=float(row.close), volume=int(row.volume),
        ))
    return out


def trailing_stop_value(entry: float, atr: float, mode: str) -> float | None:
    if mode == "off":
        return None
    if mode == "fixed3":
        return entry * (1 - 0.03)
    mult = {"atr10": 1.0, "atr15": 1.5, "atr20": 2.0}.get(mode)
    if mult is None or atr <= 0:
        return None
    return entry - mult * atr


def target_value(entry: float, mode: str) -> float | None:
    if mode == "off":
        return None
    pct = {"fixed5": 0.05, "fixed8": 0.08, "fixed10": 0.10}.get(mode)
    return entry * (1 + pct) if pct else None


def simulate_one(df_ticker: pd.DataFrame, ticker: str, args, scorer: Scorer,
                 config: SignalConfig) -> list[dict]:
    """단일 ticker 시뮬레이션. sequential overlap 적용."""
    df = df_ticker.sort_values("date").reset_index(drop=True)
    if len(df) < 70:
        return []

    trades = []
    next_allow_date = None

    for i in range(60, len(df) - 1):
        today = df.iloc[i]
        date_str = str(today["date"])

        # in-position이면 skip
        if next_allow_date is not None and date_str < next_allow_date:
            continue

        # 1차 필터
        close = float(today["close"])
        if close < config.min_close_price:
            continue

        prev_close = float(df.iloc[i - 1]["close"])
        change_pct = (close - prev_close) / prev_close * 100 if prev_close > 0 else 0
        if abs(change_pct) > config.max_change_pct:
            continue

        volume = int(today["volume"])
        trading_value = int(close * volume)
        if trading_value < args.min_trading_value:
            continue

        # 윈도우 (최대 90일)
        window = df.iloc[max(0, i - 89): i + 1]
        charts = make_charts(window)

        stock = StockData(
            code=ticker, name="", market="KOSPI", sector="auto",
            close=close, change_pct=change_pct,
            trading_value=trading_value, volume=volume, marcap=0,
            high_52w=None, low_52w=None,
        )

        score, _ = scorer.calculate(stock, charts, [], None, None)

        if args.allow_grade:
            grade = scorer.determine_grade(stock, score)
            if grade == Grade.C:
                continue
        if score.total < args.cutoff:
            continue

        # entry
        future = df.iloc[i + 1: i + 1 + args.hold_days + 1]
        if args.entry_timing == "next_open":
            if len(future) < 1:
                continue
            entry = float(future.iloc[0]["open"])
            exit_window = future.iloc[1:args.hold_days + 1]
        else:  # close
            entry = close
            exit_window = future.iloc[:args.hold_days]

        if entry <= 0 or len(exit_window) == 0:
            continue

        # exit rules
        atr = compute_atr(window, 14)
        stop = trailing_stop_value(entry, atr, args.trailing)
        target = target_value(entry, args.target)

        exit_px = float(exit_window.iloc[-1]["close"])
        reason = "time"
        exit_date = str(exit_window.iloc[-1]["date"])
        for _, row in exit_window.iterrows():
            low = float(row["low"]); high = float(row["high"])
            if stop is not None and low <= stop:
                exit_px = stop
                reason = "stop"
                exit_date = str(row["date"])
                break
            if target is not None and high >= target:
                exit_px = target
                reason = "target"
                exit_date = str(row["date"])
                break

        gross = exit_px / entry - 1.0
        net = gross - FEE_RT

        trades.append({
            "ticker": ticker, "entry_date": date_str, "exit_date": exit_date,
            "entry": round(entry, 2), "exit": round(exit_px, 2),
            "reason": reason, "score": score.total,
            "score_breakdown": score.to_dict(),
            "change_pct": round(change_pct, 2),
            "trading_value": trading_value,
            "atr": round(atr, 2),
            "gross": round(gross, 5), "net": round(net, 5),
        })
        next_allow_date = exit_date

    return trades


def stats(trades: list[dict]) -> dict:
    n = len(trades)
    if n == 0:
        return {"n": 0}
    wins = [t for t in trades if t["net"] > 0]
    losses = [t for t in trades if t["net"] <= 0]
    avg_win = mean(t["net"] for t in wins) if wins else 0.0
    avg_loss = mean(t["net"] for t in losses) if losses else 0.0
    by_reason = defaultdict(int)
    for t in trades:
        by_reason[t["reason"]] += 1
    return {
        "n": n,
        "wr": round(len(wins) / n, 4),
        "ev": round(mean(t["net"] for t in trades), 5),
        "ev_gross": round(mean(t["gross"] for t in trades), 5),
        "rr": round(abs(avg_win / avg_loss), 3) if avg_loss < 0 else 0.0,
        "avg_win": round(avg_win, 5),
        "avg_loss": round(avg_loss, 5),
        "best": round(max(t["net"] for t in trades), 5),
        "worst": round(min(t["net"] for t in trades), 5),
        "by_reason": dict(by_reason),
        "first_date": min(t["entry_date"] for t in trades),
        "last_date": max(t["entry_date"] for t in trades),
    }


def main():
    args = parse_args()

    if not PRICES_PATH.exists():
        logger.error(f"가격 데이터 없음: {PRICES_PATH}")
        sys.exit(1)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    config = SignalConfig()
    scorer = Scorer(config)

    logger.info(f"[backtest:{args.label}] 데이터 로드 중...")
    prices = pd.read_csv(PRICES_PATH, dtype={"ticker": str})
    if args.start:
        prices = prices[prices["date"] >= args.start]
    if args.end:
        prices = prices[prices["date"] <= args.end]

    tickers = list(prices["ticker"].unique())
    if args.max_rows_debug > 0:
        tickers = tickers[:args.max_rows_debug]

    logger.info(f"[backtest:{args.label}] tickers={len(tickers)} "
                f"cutoff={args.cutoff} hold={args.hold_days}d "
                f"entry={args.entry_timing} trailing={args.trailing} "
                f"target={args.target} min_tv={args.min_trading_value:,} "
                f"allow_grade={args.allow_grade}")

    by_ticker = {t: prices[prices["ticker"] == t] for t in tickers}

    all_trades = []
    for idx, ticker in enumerate(tickers):
        trades = simulate_one(by_ticker[ticker], ticker, args, scorer, config)
        all_trades.extend(trades)
        if (idx + 1) % 200 == 0:
            logger.info(f"  [{args.label}] {idx + 1}/{len(tickers)} "
                        f"trades_so_far={len(all_trades)}")

    s = stats(all_trades)
    out = {
        "label": args.label,
        "config": vars(args),
        "stats": s,
        "trades": all_trades,
    }
    out_path = OUT_DIR / f"{args.label}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    logger.info(f"[backtest:{args.label}] 완료 → {out_path}")
    logger.info(f"  trades n={s.get('n', 0)} "
                f"wr={s.get('wr', 0)*100:.1f}% "
                f"ev={s.get('ev', 0)*100:+.3f}% "
                f"rr={s.get('rr', 0):.2f} "
                f"reasons={s.get('by_reason')}")


if __name__ == "__main__":
    main()
