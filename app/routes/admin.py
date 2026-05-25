"""관리자 API (app/routes/admin.py)"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path

from flask import Blueprint, jsonify

admin_bp = Blueprint("admin", __name__)
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT / "data"

_JOBS = {
    "ocf":     {"label": "OCF 오버나이트 체크", "schedule": "08:30"},
    "update":  {"label": "데이터 업데이트",      "schedule": "08:50"},
    "vcp":     {"label": "VCP 스캔",             "schedule": "14:50"},
    "tracking":{"label": "시그널 추적",           "schedule": "14:55"},
    "summary": {"label": "일일 요약 발송",        "schedule": "15:00"},
}

_TRIGGER_MAP = {
    "ocf":      "run_ocf_check",
    "update":   "run_full_update",
    "vcp":      "run_vcp_scan",
    "tracking": "run_signal_tracking",
    "summary":  "run_daily_summary",
}


def _file_freshness(path: Path) -> str:
    if not path.exists():
        return "없음"
    mtime = datetime.fromtimestamp(path.stat().st_mtime)
    return mtime.strftime("%Y-%m-%d %H:%M:%S")


@admin_bp.route("/status")
def admin_status():
    """GET /api/admin/status — 스케줄러 잡 상태 및 데이터 신선도."""
    ocf_data = None
    ocf_path = DATA_DIR / "ocf_latest.json"
    if ocf_path.exists():
        try:
            with open(ocf_path, encoding="utf-8") as f:
                ocf_data = json.load(f)
        except Exception:
            pass

    data_freshness = {
        "ocf_latest.json":          _file_freshness(DATA_DIR / "ocf_latest.json"),
        "jongga_v2_latest.json":    _file_freshness(DATA_DIR / "jongga_v2_latest.json"),
        "signals_log_A_close.csv":  _file_freshness(DATA_DIR / "signals_log_A_close.csv"),
        "signals_log_B_next_open.csv": _file_freshness(DATA_DIR / "signals_log_B_next_open.csv"),
    }

    return jsonify({
        "jobs": {
            job_id: {
                "label":    meta["label"],
                "schedule": meta["schedule"],
                "fn":       _TRIGGER_MAP[job_id],
            }
            for job_id, meta in _JOBS.items()
        },
        "ocf_latest": ocf_data,
        "data_freshness": data_freshness,
    })


@admin_bp.route("/trigger/<job>", methods=["POST"])
def admin_trigger(job: str):
    """POST /api/admin/trigger/<job> — 스케줄러 잡 수동 실행."""
    if job not in _TRIGGER_MAP:
        return jsonify({"error": f"알 수 없는 잡: {job}"}), 400

    import importlib
    import scheduler as sched_module

    fn_name = _TRIGGER_MAP[job]
    fn = getattr(sched_module, fn_name, None)
    if fn is None:
        return jsonify({"error": f"함수 없음: {fn_name}"}), 500

    try:
        result = fn()
        return jsonify({"success": True, "job": job, "result": result})
    except Exception as e:
        logger.error(f"[admin/trigger] {job} 실패: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
