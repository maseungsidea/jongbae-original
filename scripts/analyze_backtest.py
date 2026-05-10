"""
백테 결과 분석 (scripts/analyze_backtest.py)

data/backtests/*.json 을 받아서 cumulative return + max drawdown +
Sharpe 등 자동매매 적합성 지표를 추가 계산한다.

사용법:
    python scripts/analyze_backtest.py                       # 전체
    python scripts/analyze_backtest.py --label sw_c4_off    # 특정 라벨
    python scripts/analyze_backtest.py --top 10             # EV top N
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BT_DIR = ROOT / "data" / "backtests"


def analyze(trades: list[dict], hold_days: int = 5) -> dict:
    """trades에서 추가 메트릭 계산. 기간순 정렬 가정.

    hold_days: 평균 보유 일수. Sharpe 연환산에 사용
        (periods_per_year = 252/hold_days). 일별 거래 가정의 √252 는
        멀티데이 보유에서 Sharpe 를 (252/hold_days)^0.5 배 부풀린다.
    """
    if not trades:
        return {"n": 0}

    sorted_trades = sorted(trades, key=lambda t: t["entry_date"])

    cum = 1.0
    peak = 1.0
    max_dd = 0.0
    equity_curve = []
    losing_streak_max = 0
    winning_streak_max = 0
    cur_l_streak = 0
    cur_w_streak = 0

    for t in sorted_trades:
        cum *= (1 + t["net"])
        equity_curve.append(round(cum, 4))
        if cum > peak:
            peak = cum
        dd = (cum - peak) / peak
        if dd < max_dd:
            max_dd = dd
        if t["net"] > 0:
            cur_w_streak += 1
            cur_l_streak = 0
            winning_streak_max = max(winning_streak_max, cur_w_streak)
        else:
            cur_l_streak += 1
            cur_w_streak = 0
            losing_streak_max = max(losing_streak_max, cur_l_streak)

    nets = [t["net"] for t in sorted_trades]
    mean_ret = sum(nets) / len(nets)
    var = sum((r - mean_ret) ** 2 for r in nets) / len(nets) if len(nets) > 1 else 0
    std = math.sqrt(var)
    # 멀티데이 보유 트레이드 → 1년 거래 횟수 = 252/hold_days
    periods_per_year = 252 / max(hold_days, 1)
    sharpe = (mean_ret / std) * math.sqrt(periods_per_year) if std > 0 else 0

    # 월별 거래 빈도 (entry_date 기반)
    months = set(t["entry_date"][:7] for t in sorted_trades)
    trades_per_month = len(sorted_trades) / len(months) if months else 0

    return {
        "n": len(sorted_trades),
        "cum_return": round(cum - 1, 4),     # 누적 수익률 (단리 기간)
        "max_drawdown": round(max_dd, 4),
        "sharpe_annualized": round(sharpe, 2),
        "max_losing_streak": losing_streak_max,
        "max_winning_streak": winning_streak_max,
        "trades_per_month": round(trades_per_month, 1),
        "first_date": sorted_trades[0]["entry_date"],
        "last_date": sorted_trades[-1]["entry_date"],
        "n_months": len(months),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--label", default=None)
    p.add_argument("--top", type=int, default=0,
                   help="EV 상위 N개만 표시")
    p.add_argument("--sort", choices=["ev", "cum", "sharpe", "n"],
                   default="ev")
    args = p.parse_args()

    files = sorted(BT_DIR.glob("*.json"))
    if args.label:
        files = [f for f in files if args.label in f.stem]

    rows = []
    for f in files:
        data = json.loads(f.read_text())
        hold = int(data.get("config", {}).get("hold_days", 5) or 5)
        ext = analyze(data["trades"], hold_days=hold)
        s = data["stats"]
        rows.append({
            "label": data["label"],
            **{k: data["config"].get(k) for k in
               ["cutoff", "hold_days", "entry_timing", "trailing", "target",
                "partial_exit", "min_trading_value", "allow_grade", "max_gap_pct"]},
            "n": s.get("n", 0),
            "wr": s.get("wr", 0),
            "ev": s.get("ev", 0),
            "rr": s.get("rr", 0),
            **ext,
        })

    sort_keys = {"ev": "ev", "cum": "cum_return", "sharpe": "sharpe_annualized", "n": "n"}
    rows.sort(key=lambda r: -(r.get(sort_keys[args.sort]) or 0))
    if args.top > 0:
        rows = rows[:args.top]

    print(f"\n{'label':28s} | {'n':5s} | {'WR':6s} | {'EV':8s} | {'RR':5s} | "
          f"{'cum':8s} | {'mdd':8s} | {'shp':5s} | {'tpm':5s} | {'maxLstr':7s}")
    print("-" * 120)
    for r in rows:
        print(f"{r['label']:28s} | {r['n']:5d} | "
              f"{(r['wr'] or 0)*100:5.1f}% | "
              f"{(r['ev'] or 0)*100:+7.3f}% | "
              f"{r['rr']:5.2f} | "
              f"{(r['cum_return'] or 0)*100:+7.2f}% | "
              f"{(r['max_drawdown'] or 0)*100:+7.2f}% | "
              f"{r['sharpe_annualized']:+5.2f} | "
              f"{r['trades_per_month']:5.1f} | "
              f"{r['max_losing_streak']:7d}")


if __name__ == "__main__":
    main()
