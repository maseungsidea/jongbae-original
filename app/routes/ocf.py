"""OCF 오버나이트 리스크 API (app/routes/ocf.py)"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from flask import Blueprint, jsonify

ocf_bp = Blueprint("ocf", __name__)
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT / "data"


@ocf_bp.route("/latest")
def ocf_latest():
    """GET /api/ocf/latest — 오늘의 OCF 체크 결과."""
    path = DATA_DIR / "ocf_latest.json"
    if not path.exists():
        return jsonify({
            "error": "OCF 데이터 없음",
            "detail": "매일 08:30 KST 이후 업데이트됩니다.",
        }), 404
    with open(path, encoding="utf-8") as f:
        return jsonify(json.load(f))
