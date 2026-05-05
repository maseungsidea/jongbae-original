"""
종가베팅 가설 sweep (scripts/sweep_jongga.py)

backtest_jongga.py 의 단일 실행을 grid 형태로 돌려서
유니버스·진입타이밍·cutoff·exit 룰별 EV 변별력을 측정한다.

Variants:
  cutoff      : 4 / 5 / 6
  hold_days   : 3 / 5 / 7
  entry       : close / next_open
  trailing    : off / fixed3 / atr15 / atr20
  target      : off / fixed5 / fixed8
  min_tv      : 50억 / 100억 / 500억

→ 3 × 3 × 2 × 4 × 3 × 3 = 648 조합. 무거우니
  default는 의미있는 ~30 조합만 (선별)
  --grid full 시 전체.

출력: docs/jongga_sweep_report.md
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from itertools import product
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BT_DIR = ROOT / "data" / "backtests"
SCRIPT = ROOT / "scripts" / "backtest_jongga.py"
REPORT = ROOT / "docs" / "jongga_sweep_report.md"

GRID_QUICK = {
    "cutoff":   [4, 5, 6],
    "hold":     [3, 5, 7],
    "entry":    ["close", "next_open"],
    "trailing": ["off", "atr15", "fixed3"],
    "target":   ["off", "fixed5"],
    "min_tv":   [10_000_000_000],   # 100억 고정
}

GRID_FULL = {
    "cutoff":   [3, 4, 5, 6, 7],
    "hold":     [3, 5, 7],
    "entry":    ["close", "next_open"],
    "trailing": ["off", "atr10", "atr15", "atr20", "fixed3"],
    "target":   ["off", "fixed5", "fixed8"],
    "min_tv":   [5_000_000_000, 10_000_000_000, 50_000_000_000],
}


def run_one(args: dict) -> dict:
    label = (f"sw_c{args['cutoff']}_h{args['hold']}d_{args['entry']}_"
             f"{args['trailing']}_{args['target']}_tv{args['min_tv']//1_000_000_000}")
    out_path = BT_DIR / f"{label}.json"

    cmd = [
        sys.executable, str(SCRIPT),
        "--cutoff", str(args["cutoff"]),
        "--hold-days", str(args["hold"]),
        "--entry-timing", args["entry"],
        "--trailing", args["trailing"],
        "--target", args["target"],
        "--min-trading-value", str(args["min_tv"]),
        "--label", label,
    ]
    print(f">>> {label}")
    res = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"  ERROR: {res.stderr[-300:]}")
        return None
    if not out_path.exists():
        return None
    data = json.loads(out_path.read_text())
    return {"label": label, **args, **data["stats"]}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--grid", choices=["quick", "full"], default="quick")
    p.add_argument("--limit", type=int, default=0,
                   help="조합 수 제한 (0=무제한)")
    args = p.parse_args()

    grid = GRID_FULL if args.grid == "full" else GRID_QUICK
    keys = list(grid.keys())
    combos = [dict(zip(keys, vals)) for vals in product(*grid.values())]
    if args.limit:
        combos = combos[:args.limit]

    print(f"sweep grid={args.grid}, combos={len(combos)}")
    BT_DIR.mkdir(parents=True, exist_ok=True)

    results = []
    for c in combos:
        r = run_one(c)
        if r:
            results.append(r)

    results.sort(key=lambda x: -(x.get("ev") or -1))

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# 종가베팅 sweep 결과", "",
             f"- 조합 수: {len(results)}",
             f"- grid: {args.grid}",
             "",
             "## Top 20 by EV (net)",
             "",
             "| rank | cutoff | hold | entry | trailing | target | min_tv(억) | n | WR | EV | RR | reasons |",
             "|------|--------|------|-------|----------|--------|-----------|---|----|----|----|---------|"]

    for i, r in enumerate(results[:20], 1):
        reasons = r.get("by_reason", {})
        rsn = ",".join(f"{k}={v}" for k, v in reasons.items())
        lines.append(
            f"| {i} | {r['cutoff']} | {r['hold']}d | {r['entry']:>9} "
            f"| {r['trailing']:>7} | {r['target']:>7} | {r['min_tv']//100_000_000} "
            f"| {r.get('n', 0)} | {(r.get('wr') or 0)*100:.1f}% "
            f"| **{(r.get('ev') or 0)*100:+.3f}%** | {r.get('rr', 0):.2f} | {rsn} |"
        )

    lines += ["", "## Bottom 5", "",
              "| cutoff | hold | entry | trailing | target | n | WR | EV |",
              "|--------|------|-------|----------|--------|---|----|----|"]
    for r in results[-5:]:
        lines.append(
            f"| {r['cutoff']} | {r['hold']}d | {r['entry']} | {r['trailing']} "
            f"| {r['target']} | {r.get('n', 0)} | {(r.get('wr') or 0)*100:.1f}% "
            f"| {(r.get('ev') or 0)*100:+.3f}% |"
        )

    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n=== TOP 5 ===")
    for r in results[:5]:
        print(f"  {r['label']:55s} n={r.get('n',0):5d} "
              f"WR={(r.get('wr') or 0)*100:5.1f}% EV={(r.get('ev') or 0)*100:+.3f}%")
    print(f"\nreport: {REPORT}")


if __name__ == "__main__":
    main()
