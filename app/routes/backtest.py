"""백테 파라미터 비교 API (app/routes/backtest.py)"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from flask import Blueprint, jsonify, request

backtest_bp = Blueprint("backtest", __name__)
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent
BT_DIR = ROOT / "data" / "backtests"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@backtest_bp.route("/latest")
def backtest_latest():
    """GET /api/kr/backtest/latest — 최신 OCF 백테 비교 결과."""
    path = BT_DIR / "sw_nopen_gap1_ocf_comparison.json"
    if not path.exists():
        return jsonify({"error": "백테 결과 없음. backtest_with_ocf.py 를 먼저 실행하세요."}), 404
    with open(path, encoding="utf-8") as f:
        return jsonify(json.load(f))


@backtest_bp.route("/run", methods=["POST"])
def backtest_run():
    """POST /api/kr/backtest/run — OCF 파라미터 변경 후 비교 실행.

    Body (JSON):
    {
      "label": "sw_nopen_gap1",
      "params": {
        "sp500_drop_pct":   -1.5,
        "vix_spike_abs":    25.0,
        "ewy_drop_pct":     -1.5,
        "usdkrw_abs":       1520.0,
        "usdkrw_spike_pct": 1.5
      }
    }
    """
    body = request.get_json(silent=True) or {}
    label = body.get("label", "sw_nopen_gap1")
    params = body.get("params", {})

    bt_path = BT_DIR / f"{label}.json"
    if not bt_path.exists():
        return jsonify({"error": f"백테 파일 없음: {label}.json"}), 404

    try:
        from engine.ocf import OCFConfig
        from scripts.backtest_with_ocf import precompute_ocf_flags, run_comparison

        # OCFConfig 파라미터 오버라이드
        config_kwargs = {}
        float_fields = [
            "sp500_drop_pct", "vix_spike_abs", "vix_spike_pct",
            "ewy_drop_pct", "usdkrw_abs", "usdkrw_spike_pct",
        ]
        for field in float_fields:
            if field in params:
                config_kwargs[field] = float(params[field])

        config = OCFConfig(**config_kwargs)

        flags = precompute_ocf_flags("2024-01-01", "2026-04-30", config=config)
        result = run_comparison(str(bt_path), flags)

        # 결과 캐시 저장
        out_path = BT_DIR / f"{label}_ocf_comparison.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        return jsonify(result)

    except Exception as e:
        logger.error(f"[backtest/run] 오류: {e}")
        return jsonify({"error": str(e)}), 500
