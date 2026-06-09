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
import os
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean

# 백테는 수십만 건 채점 → Telegram 알림 강제 비활성 (utils.notifier 가 이 env 를 본다)
os.environ.setdefault("JONGGA_NOTIFY", "0")

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.config import Grade, SignalConfig
from engine.models import ChartData, StockData, SupplyData
from engine.scorer import Scorer
from engine.exit_simulator import ExitParams, simulate_exit
from engine.trailing_stop import compute_atr as _wilder_atr  # 라이브 진입 게이트와 동일 추정기

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

PRICES_PATH = ROOT / "data" / "daily_prices.csv"
SUPPLY_PATH = ROOT / "data" / "naver_supply.csv"
MARCAP_PATH = ROOT / "data" / "korean_stocks_list.csv"
OUT_DIR = ROOT / "data" / "backtests"
FEE_RT = 0.0021  # 한국 round-trip 수수료 + 세금


def load_marcap_lookup() -> dict[str, int]:
    """korean_stocks_list.csv → {ticker: marcap} dict. BOM 처리 포함."""
    if not MARCAP_PATH.exists():
        logger.warning(f"[backtest] 시총 파일 없음: {MARCAP_PATH} → 시총 필터 무력화")
        return {}
    df = pd.read_csv(MARCAP_PATH, dtype={"ticker": str}, encoding="utf-8-sig")
    df["ticker"] = df["ticker"].str.zfill(6)
    return dict(zip(df["ticker"], df["marcap"].astype(int)))


def load_supply_lookup() -> dict | None:
    """naver_supply.csv 를 (ticker, date) → (inst_net, foreign_net) dict 로 로드."""
    if not SUPPLY_PATH.exists():
        return None
    df = pd.read_csv(SUPPLY_PATH, dtype={"ticker": str}, parse_dates=["date"])
    df["ticker"] = df["ticker"].str.zfill(6)
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    out: dict = {}
    for r in df.itertuples(index=False):
        out[(r.ticker, r.date)] = (int(r.inst_net), int(r.foreign_net))
    return out


def lookup_supply(
    sup: dict | None, ticker: str, date_str: str, lookback: int = 5
) -> SupplyData | None:
    """신호일 D 의 D-(lookback-1) ~ D 누적 외인/기관 net buy 반환."""
    if sup is None:
        return None
    target = pd.Timestamp(date_str)
    foreign_total = 0
    inst_total = 0
    found = False
    for i in range(lookback):
        d = (target - pd.Timedelta(days=i)).strftime("%Y-%m-%d")
        if (ticker, d) in sup:
            inst, foreign = sup[(ticker, d)]
            inst_total += inst
            foreign_total += foreign
            found = True
    if not found:
        return None
    return SupplyData(foreign_buy_5d=foreign_total, inst_buy_5d=inst_total)


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--cutoff", type=int, default=5,
                   help="총점 cutoff (12점 만점, 백테스트는 7점 cap)")
    p.add_argument("--min-trading-value", type=int, default=10_000_000_000,
                   help="최소 거래대금 (원). default 100억")
    p.add_argument("--allow-grade", action="store_true",
                   help="determine_grade 통과 + cutoff (운영과 동일)")
    p.add_argument("--hold-days", type=int, default=5)
    p.add_argument("--exit-engine", choices=["static", "faithful"], default="faithful",
                   help="faithful=라이브 청산 로직(trailing ratchet·Day-1 보호·hard_stop·분할익절) "
                        "재현. static=구 고정-stop 근사(--trailing/--target/--partial-exit 사용)")
    p.add_argument("--close-entry-bar", choices=["eval", "skip"], default="skip",
                   help="(faithful·close 전용) 진입 바 청산 평가 여부. "
                        "skip=신호일 이후 바부터 평가(라이브 기본, Sprint2 d0 lookahead 방어 후 "
                        "signal_tracker.py:475~ 와 정합). eval=진입 바도 평가(레거시 fall-through "
                        "재현용, d0 phantom hard_stop 포함 — 비교/회귀 측정 전용)")
    p.add_argument("--entry-timing", choices=["close", "next_open"], default="close")
    p.add_argument("--max-atr-pct", type=float, default=None,
                   help="진입가 대비 ATR%% 상한. 초과 종목은 진입 skip (고변동 노이즈 hard_stop 회피). "
                        "예: 6.0 → ATR/entry>6%% 종목 제외")
    p.add_argument("--trailing", choices=["off", "atr10", "atr15", "atr20", "fixed3"],
                   default="atr15", help="손절 룰. fixed3=고정 -3%")
    p.add_argument("--target", choices=["off", "fixed5", "fixed8", "fixed10"],
                   default="fixed5", help="익절. fixed5=+5%")
    p.add_argument("--partial-exit", action="store_true",
                   help="부분 청산: target 도달 시 50% 청산, 나머지는 trailing/time")
    p.add_argument("--max-gap-pct", type=float, default=None,
                   help="next_open 진입 시 갭 +X% 이상이면 skip (예: 2.0)")
    p.add_argument("--regime", choices=["any", "bull"], default="any",
                   help="bull = KOSPI EMA20>EMA60 인 거래일만 진입")
    p.add_argument("--start", default=None, help="백테스트 시작일 (YYYY-MM-DD)")
    p.add_argument("--end", default=None, help="백테스트 종료일")
    p.add_argument("--label", default="run", help="결과 파일 라벨")
    p.add_argument("--max-marcap", type=int, default=None,
                   help="시총 상한(원). 초과 종목 제외. None=무제한 (예: 10000000000000 = 10조)")
    p.add_argument("--max-rows-debug", type=int, default=0,
                   help="디버그: ticker 수 제한 (0=전체)")
    p.add_argument("--supply", choices=["on", "off"], default="off",
                   help="data/naver_supply.csv 의 외인/기관 5일 누적을 점수에 반영")
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
                 config: SignalConfig, supply_lookup: dict | None = None) -> list[dict]:
    """단일 ticker 시뮬레이션. sequential overlap 적용."""
    df = df_ticker.sort_values("date").reset_index(drop=True)
    if len(df) < 70:
        return []

    trades = []
    next_allow_date = None

    # faithful 엔진: 라이브 SignalConfig 값을 그대로 미러 (max_hold_days 만 --hold-days 로 오버라이드)
    ep = ExitParams(
        atr_period=config.atr_period,
        atr_multiplier=config.atr_multiplier,
        trailing_min_hold_days=config.trailing_min_hold_days,
        max_hold_days=args.hold_days,
        partial_exit_enabled=config.partial_exit_enabled,
        partial_exit_target_pct=config.partial_exit_target_pct,
        partial_exit_ratio=config.partial_exit_ratio,
        hard_stop_floor_pct=config.hard_stop_floor_pct,
        sanghan_exit_enabled=config.sanghan_exit_enabled,
        sanghan_threshold_pct=config.sanghan_threshold_pct,
        rsi_overbought_exit_enabled=config.rsi_overbought_exit_enabled,
        rsi_overbought_threshold=config.rsi_overbought_threshold,
    )

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

        sup = lookup_supply(supply_lookup, ticker, date_str) if supply_lookup else None
        score, _ = scorer.calculate(stock, charts, [], sup, None)

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
            # 갭 필터: 익일 시초가 갭이 너무 크면 skip
            if args.max_gap_pct is not None:
                gap_pct = (entry / close - 1.0) * 100
                if gap_pct > args.max_gap_pct:
                    continue
            exit_window = future.iloc[1:args.hold_days + 1]
        else:  # close
            entry = close
            exit_window = future.iloc[:args.hold_days]

        if entry <= 0 or len(exit_window) == 0:
            continue

        # exit rules
        atr = compute_atr(window, 14)

        # ── 변동성 진입 필터 (Sprint 2 후보 2): 진입가 대비 ATR% 가 너무 높은
        #    고변동 종목은 -8% hard_stop 에 노이즈로 걸려 EV 를 갉아먹는다.
        #    ATR% 는 진입 시점에 알 수 있으므로 lookahead 아님. (근본 진입 메커니즘 변경)
        #    ※ 게이트 ATR 은 라이브(engine.generator)와 동일하게 Wilder ATR 의 마지막 값
        #      (engine.trailing_stop.compute_atr)을 써야 검증값이 실거동을 그대로 재현한다.
        #      단순평균 atr(=compute_atr(window)) 은 legacy static-stop 분기/기록용으로만 유지.
        if args.max_atr_pct is not None and entry > 0:
            _wilder = _wilder_atr(
                [c.high for c in charts],
                [c.low for c in charts],
                [c.close for c in charts],
                period=SignalConfig().atr_period,  # 라이브 generator 와 동일 period (하드코딩 14 금지 — 재튜닝 시 divergence 방지)
            )
            atr_gate = _wilder[-1] if _wilder else 0.0
            atr_pct = atr_gate / entry * 100
            if atr_pct > args.max_atr_pct:
                continue

        if args.exit_engine == "faithful":
            # 라이브 청산 로직 재현 (engine.exit_simulator) — static 근사 대체
            # 진입 체결 바: close=신호바 i, next_open=익일 i+1.
            # 라이브(signal_tracker.py:432-434)는 next_open 진입 당일 평가를 skip → 첫 평가는 i+2.
            # 따라서 entry_idx 를 진입 체결 바로 넘겨 sim 의 eval(entry_idx+1)이 i+2 부터 시작하게 한다.
            entry_bar = i if args.entry_timing == "close" else i + 1
            start = max(0, i - 89)
            sl = df.iloc[start: entry_bar + args.hold_days + 2]
            entry_local = entry_bar - start
            # close 는 라이브 fall-through 로 진입 바부터 평가(옵션), next_open 은 진입 당일 skip
            eval_entry_bar = (args.entry_timing == "close" and args.close_entry_bar == "eval")
            res = simulate_exit(
                entry_price=entry,
                highs=[float(x) for x in sl["high"].tolist()],
                lows=[float(x) for x in sl["low"].tolist()],
                closes=[float(x) for x in sl["close"].tolist()],
                entry_idx=entry_local,
                params=ep,
                eval_entry_bar=eval_entry_bar,
            )
            exit_px = round(res.exit_price, 2)
            reason = res.exit_reason
            gross = res.return_pct / 100.0   # 분할 가중평균이 이미 반영된 gross
            # 청산 바 절대 df 인덱스 = start + (entry_local + bars_held) = 슬라이스 청산 루프 인덱스
            exit_df_idx = min(len(df) - 1, start + entry_local + res.bars_held)
            exit_date = str(df.iloc[exit_df_idx]["date"])
        else:
            stop = trailing_stop_value(entry, atr, args.trailing)
            target = target_value(entry, args.target)

            # 청산 시뮬레이션 (구 static-stop 근사)
            exit_px = float(exit_window.iloc[-1]["close"])
            reason = "time"
            exit_date = str(exit_window.iloc[-1]["date"])
            partial_done = False
            partial_return = 0.0   # 부분 청산 시 50% 누적 수익 (gross 기준)

            for _, row in exit_window.iterrows():
                low = float(row["low"]); high = float(row["high"])
                row_date = str(row["date"])

                # target hit
                if target is not None and high >= target and not partial_done:
                    if args.partial_exit:
                        # 50% 부분 청산: 나머지 50%는 hold 지속, target 무력화
                        partial_done = True
                        partial_return = 0.5 * (target / entry - 1.0)
                        # 다음 row로 (이 row에서 stop 동시 hit 가능성은 무시)
                        continue
                    else:
                        exit_px = target; reason = "target"; exit_date = row_date
                        break

                # stop hit
                if stop is not None and low <= stop:
                    if partial_done:
                        remainder = 0.5 * (stop / entry - 1.0)
                        full_gross = partial_return + remainder
                        exit_px = entry * (1 + full_gross)   # weighted exit (가상가)
                        reason = "partial_stop"
                    else:
                        exit_px = stop
                        reason = "stop"
                    exit_date = row_date
                    break
            else:
                # break 없이 종료 → time exit
                last_close = float(exit_window.iloc[-1]["close"])
                if partial_done:
                    remainder = 0.5 * (last_close / entry - 1.0)
                    full_gross = partial_return + remainder
                    exit_px = entry * (1 + full_gross)
                    reason = "partial_time"
                else:
                    exit_px = last_close
                    reason = "time"

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
    # supply 옵션이 켜져 있으면 백테 한정으로 supply_enabled=True
    config.supply_enabled = (args.supply == "on")
    scorer = Scorer(config)

    supply_lookup = load_supply_lookup() if args.supply == "on" else None
    if args.supply == "on":
        if supply_lookup is None:
            logger.warning(f"[backtest] supply=on 이지만 {SUPPLY_PATH} 없음 → 0 처리")
        else:
            logger.info(f"[backtest] supply 로드: {len(supply_lookup)} (ticker,date) 행")

    logger.info(f"[backtest:{args.label}] 데이터 로드 중...")
    prices = pd.read_csv(PRICES_PATH, dtype={"ticker": str})
    if args.start:
        prices = prices[prices["date"] >= args.start]
    if args.end:
        prices = prices[prices["date"] <= args.end]

    tickers = list(prices["ticker"].unique())
    if args.max_rows_debug > 0:
        tickers = tickers[:args.max_rows_debug]

    if args.max_marcap is not None:
        marcap_lookup = load_marcap_lookup()
        before = len(tickers)
        no_marcap = [t for t in tickers if t not in marcap_lookup]
        dropped = [t for t in tickers if t in marcap_lookup and marcap_lookup[t] > args.max_marcap]
        tickers = [t for t in tickers if t not in marcap_lookup or marcap_lookup[t] <= args.max_marcap]
        logger.info(
            f"[backtest:{args.label}] 시총 필터 max_marcap={args.max_marcap:,}원: "
            f"before={before} dropped={len(dropped)} no_marcap(kept)={len(no_marcap)} after={len(tickers)}"
        )

    logger.info(f"[backtest:{args.label}] tickers={len(tickers)} "
                f"cutoff={args.cutoff} hold={args.hold_days}d "
                f"entry={args.entry_timing} trailing={args.trailing} "
                f"target={args.target} min_tv={args.min_trading_value:,} "
                f"allow_grade={args.allow_grade}")

    by_ticker = {t: prices[prices["ticker"] == t] for t in tickers}

    all_trades = []
    for idx, ticker in enumerate(tickers):
        trades = simulate_one(by_ticker[ticker], ticker, args, scorer, config, supply_lookup)
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
