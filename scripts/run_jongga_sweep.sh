#!/bin/bash
# 종가베팅 빠른 sweep — 12 의미있는 변형
set -e
cd "$(dirname "$0")/.."
source .venv/bin/activate

run() {
  python scripts/backtest_jongga.py "$@" 2>&1 | tail -2
  echo "---"
}

echo "=== [1] baseline (이미 실행됨, skip) ==="

echo "=== [2] cutoff 6 + grade-pass (운영 등가) ==="
run --cutoff 6 --allow-grade --hold-days 5 --entry-timing close --trailing atr15 --target fixed5 --min-trading-value 10000000000 --label sw_grade6

echo "=== [3] cutoff 4 (완화) ==="
run --cutoff 4 --hold-days 5 --entry-timing close --trailing atr15 --target fixed5 --min-trading-value 10000000000 --label sw_c4

echo "=== [4] hold 3d ==="
run --cutoff 5 --hold-days 3 --entry-timing close --trailing atr15 --target fixed5 --min-trading-value 10000000000 --label sw_h3

echo "=== [5] hold 7d ==="
run --cutoff 5 --hold-days 7 --entry-timing close --trailing atr15 --target fixed5 --min-trading-value 10000000000 --label sw_h7

echo "=== [6] entry next_open ==="
run --cutoff 5 --hold-days 5 --entry-timing next_open --trailing atr15 --target fixed5 --min-trading-value 10000000000 --label sw_nopen

echo "=== [7] trailing fixed3 (고정 -3%) ==="
run --cutoff 5 --hold-days 5 --entry-timing close --trailing fixed3 --target fixed5 --min-trading-value 10000000000 --label sw_fix3

echo "=== [8] trailing off (target only) ==="
run --cutoff 5 --hold-days 5 --entry-timing close --trailing off --target fixed5 --min-trading-value 10000000000 --label sw_nostop

echo "=== [9] target off (trailing only) ==="
run --cutoff 5 --hold-days 5 --entry-timing close --trailing atr15 --target off --min-trading-value 10000000000 --label sw_notarget

echo "=== [10] atr20 (loose stop) ==="
run --cutoff 5 --hold-days 5 --entry-timing close --trailing atr20 --target fixed5 --min-trading-value 10000000000 --label sw_atr20

echo "=== [11] universe 대형주 (min_tv 500억) ==="
run --cutoff 5 --hold-days 5 --entry-timing close --trailing atr15 --target fixed5 --min-trading-value 50000000000 --label sw_tv500

echo "=== [12] universe 광범위 (min_tv 50억) ==="
run --cutoff 5 --hold-days 5 --entry-timing close --trailing atr15 --target fixed5 --min-trading-value 5000000000 --label sw_tv50

echo "=== ALL DONE ==="
