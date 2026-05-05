"""기존 sweep 결과의 config 를 가져와 --supply on 으로 재실행.

핵심 5개만 default. 새 라벨은 <orig>_supply.

사용:
    python3 scripts/rerun_with_supply.py
    python3 scripts/rerun_with_supply.py --all       # 33개 전체
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BT = ROOT / "data" / "backtests"
SCRIPT = ROOT / "scripts" / "backtest_jongga.py"

CORE_LABELS = [
    "baseline",
    "sw_pe_t8",
    "sw_nopen_gap1",
    "sw_h20_off",
    "sw_c4_pe_t8_h10",
]


def cmd_for(label: str, cfg: dict, new_label: str) -> list[str]:
    cmd = [
        sys.executable, str(SCRIPT),
        "--label", new_label,
        "--cutoff", str(cfg["cutoff"]),
        "--hold-days", str(cfg["hold_days"]),
        "--entry-timing", cfg["entry_timing"],
        "--trailing", cfg["trailing"],
        "--target", cfg["target"],
        "--min-trading-value", str(cfg["min_trading_value"]),
        "--supply", "on",
    ]
    if cfg.get("allow_grade"):
        cmd.append("--allow-grade")
    if cfg.get("partial_exit"):
        cmd.append("--partial-exit")
    if cfg.get("max_gap_pct") is not None:
        cmd.extend(["--max-gap-pct", str(cfg["max_gap_pct"])])
    return cmd


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--all", action="store_true", help="33개 전체 재실행")
    args = p.parse_args()

    targets = []
    for f in sorted(BT.iterdir()):
        if not f.name.endswith(".json"):
            continue
        label = f.stem
        if label.startswith("_") or label.endswith("_supply"):
            continue
        if not args.all and label not in CORE_LABELS:
            continue
        blob = json.loads(f.read_text())
        targets.append((label, blob.get("config", {})))

    print(f"[rerun] {len(targets)} sweep 재실행 (--supply on)")
    for label, cfg in targets:
        new_label = label + "_supply"
        out = BT / f"{new_label}.json"
        if out.exists():
            print(f"  skip {new_label} (이미 존재)")
            continue
        cmd = cmd_for(label, cfg, new_label)
        print(f"  → {new_label}")
        subprocess.run(cmd, check=False)


if __name__ == "__main__":
    main()
