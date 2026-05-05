#!/bin/bash
# 종가베팅 추가 sweep — 1차 결과 기반 확장 가설
# 핵심: +5% 익절이 winner를 자른다 → 익절 늘리거나 끄기 + stop variation
set -e
cd "$(dirname "$0")/.."
source .venv/bin/activate

run() {
  python scripts/backtest_jongga.py "$@" 2>&1 | tail -2
  echo "---"
}

echo "=== [13] target=fixed8 (익절 +8%) ==="
run --cutoff 5 --hold-days 5 --entry-timing close --trailing atr15 --target fixed8 --min-trading-value 10000000000 --label sw_t8

echo "=== [14] target=fixed10 (익절 +10%) ==="
run --cutoff 5 --hold-days 5 --entry-timing close --trailing atr15 --target fixed10 --min-trading-value 10000000000 --label sw_t10

echo "=== [15] target=off + atr10 (tight stop) ==="
run --cutoff 5 --hold-days 5 --entry-timing close --trailing atr10 --target off --min-trading-value 10000000000 --label sw_off_atr10

echo "=== [16] target=off + atr20 (loose stop) ==="
run --cutoff 5 --hold-days 5 --entry-timing close --trailing atr20 --target off --min-trading-value 10000000000 --label sw_off_atr20

echo "=== [17] cutoff=4 + target=off + atr15 ==="
run --cutoff 4 --hold-days 5 --entry-timing close --trailing atr15 --target off --min-trading-value 10000000000 --label sw_c4_off

echo "=== [18] cutoff=4 + target=fixed8 ==="
run --cutoff 4 --hold-days 5 --entry-timing close --trailing atr15 --target fixed8 --min-trading-value 10000000000 --label sw_c4_t8

echo "=== [19] hold=10d + target=off + atr15 ==="
run --cutoff 5 --hold-days 10 --entry-timing close --trailing atr15 --target off --min-trading-value 10000000000 --label sw_h10_off

echo "=== [20] cutoff=6 + grade + target=off ==="
run --cutoff 6 --allow-grade --hold-days 5 --entry-timing close --trailing atr15 --target off --min-trading-value 10000000000 --label sw_grade6_off

echo "=== ALL DONE ==="
