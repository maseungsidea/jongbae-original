#!/bin/bash
# 종가베팅 sweep #3 — hold/atr 정밀 탐색
# Sweep #2에서 hold=10d + target=off + atr15가 best였음. 더 늘리면? atr 더 변형하면?
set -e
cd "$(dirname "$0")/.."
source .venv/bin/activate

run() {
  python scripts/backtest_jongga.py "$@" 2>&1 | tail -2
  echo "---"
}

echo "=== [21] hold=12d + target=off + atr15 ==="
run --cutoff 5 --hold-days 12 --entry-timing close --trailing atr15 --target off --min-trading-value 10000000000 --label sw_h12_off

echo "=== [22] hold=15d + target=off + atr15 ==="
run --cutoff 5 --hold-days 15 --entry-timing close --trailing atr15 --target off --min-trading-value 10000000000 --label sw_h15_off

echo "=== [23] hold=20d + target=off + atr15 ==="
run --cutoff 5 --hold-days 20 --entry-timing close --trailing atr15 --target off --min-trading-value 10000000000 --label sw_h20_off

echo "=== [24] hold=10d + target=off + atr10 ==="
run --cutoff 5 --hold-days 10 --entry-timing close --trailing atr10 --target off --min-trading-value 10000000000 --label sw_h10_atr10_off

echo "=== [25] hold=15d + target=off + atr10 ==="
run --cutoff 5 --hold-days 15 --entry-timing close --trailing atr10 --target off --min-trading-value 10000000000 --label sw_h15_atr10_off

echo "=== [26] cutoff=4 + hold=10d + target=off + atr15 ==="
run --cutoff 4 --hold-days 10 --entry-timing close --trailing atr15 --target off --min-trading-value 10000000000 --label sw_c4_h10_off

echo "=== [27] cutoff=4 + hold=10d + target=off + atr10 ==="
run --cutoff 4 --hold-days 10 --entry-timing close --trailing atr10 --target off --min-trading-value 10000000000 --label sw_c4_h10_atr10_off

echo "=== ALL DONE ==="
