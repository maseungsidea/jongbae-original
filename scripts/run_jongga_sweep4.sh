#!/bin/bash
# 종가베팅 sweep #4 — 부분 청산 + 갭 필터 (코드 추가 후)
set -e
cd "$(dirname "$0")/.."
source .venv/bin/activate

run() {
  python scripts/backtest_jongga.py "$@" 2>&1 | tail -2
  echo "---"
}

echo "=== [28] partial_exit + target=fixed5 + atr15 ==="
run --cutoff 5 --hold-days 5 --entry-timing close --trailing atr15 --target fixed5 --partial-exit --min-trading-value 10000000000 --label sw_pe_t5

echo "=== [29] partial_exit + target=fixed8 + atr15 ==="
run --cutoff 5 --hold-days 5 --entry-timing close --trailing atr15 --target fixed8 --partial-exit --min-trading-value 10000000000 --label sw_pe_t8

echo "=== [30] partial_exit + target=fixed10 + hold=10d ==="
run --cutoff 5 --hold-days 10 --entry-timing close --trailing atr15 --target fixed10 --partial-exit --min-trading-value 10000000000 --label sw_pe_t10_h10

echo "=== [31] next_open + gap≤2% + atr15 + target=off ==="
run --cutoff 5 --hold-days 5 --entry-timing next_open --trailing atr15 --target off --max-gap-pct 2.0 --min-trading-value 10000000000 --label sw_nopen_gap2

echo "=== [32] next_open + gap≤1% + atr15 + target=off ==="
run --cutoff 5 --hold-days 5 --entry-timing next_open --trailing atr15 --target off --max-gap-pct 1.0 --min-trading-value 10000000000 --label sw_nopen_gap1

echo "=== [33] cutoff=4 + partial_exit + target=fixed8 + hold=10d ==="
run --cutoff 4 --hold-days 10 --entry-timing close --trailing atr15 --target fixed8 --partial-exit --min-trading-value 10000000000 --label sw_c4_pe_t8_h10

echo "=== ALL DONE ==="
