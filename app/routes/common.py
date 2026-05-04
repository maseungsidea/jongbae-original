"""
공통 API Blueprint (app/routes/common.py)

/api/ 하위 공통 엔드포인트 8개를 구현합니다.
- /api/health        : 서버 상태 확인
- /api/chatbot       : AI 챗봇 대화
- /api/signals/save  : 시그널 저장
- /api/signals/exit  : 시그널 청산 업데이트
- /api/signals/open  : 미청산 시그널 조회
- /api/performance   : 전체 성과 요약
- /api/cache/clear   : 캐시 초기화
- /api/config        : 현재 설정값 조회
"""

from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

common_bp = Blueprint("common", __name__)
logger = logging.getLogger(__name__)


def _error(msg: str, status: int = 500):
    return jsonify({"error": msg}), status


# ─────────────────────────────────────────
# 헬스 체크
# ─────────────────────────────────────────

@common_bp.route("/health")
def health():
    """GET /api/health - 서버 상태 확인"""
    return jsonify({"status": "ok", "service": "closing-bet-api"})


# ─────────────────────────────────────────
# AI 챗봇
# ─────────────────────────────────────────

@common_bp.route("/chatbot", methods=["POST"])
def chatbot():
    """
    POST /api/chatbot
    AI 챗봇 대화

    Body:
    {
      "message": "삼성전자 분석해줘",
      "session_id": "user_001"  (optional)
    }
    """
    body = request.get_json(silent=True) or {}
    message = body.get("message", "").strip()
    session_id = body.get("session_id", "default")

    if not message:
        return _error("메시지가 비어있습니다.", 400)

    try:
        from chatbot import get_chatbot
        bot = get_chatbot()
        response = bot.chat(message, session_id=session_id)
        return jsonify({"response": response, "session_id": session_id})
    except Exception as e:
        logger.error(f"[/chatbot] {e}")
        return _error(str(e))


# ─────────────────────────────────────────
# 시그널 관리
# ─────────────────────────────────────────

@common_bp.route("/signals/save", methods=["POST"])
def save_signal():
    """
    POST /api/signals/save
    시그널을 signals_log.csv에 저장

    Body: Signal.to_dict() 형태의 JSON
    """
    body = request.get_json(silent=True)
    if not body:
        return _error("요청 본문이 없습니다.", 400)

    try:
        import signal_tracker
        success = signal_tracker.save_signal(body)
        if not success:
            return _error("저장 실패 (중복 또는 오류)", 409)
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"[/signals/save] {e}")
        return _error(str(e))


@common_bp.route("/signals/exit", methods=["POST"])
def exit_signal():
    """
    POST /api/signals/exit
    시그널 청산 정보 업데이트

    Body:
    {
      "ticker": "005930",
      "signal_date": "2024-01-15",
      "exit_price": 72000,
      "exit_reason": "take_profit"
    }
    """
    body = request.get_json(silent=True) or {}
    ticker = body.get("ticker", "")
    signal_date = body.get("signal_date", "")
    exit_price = float(body.get("exit_price", 0))
    exit_reason = body.get("exit_reason", "manual")

    if not ticker or not signal_date or exit_price <= 0:
        return _error("필수 필드 누락: ticker, signal_date, exit_price", 400)

    try:
        import signal_tracker
        success = signal_tracker.update_exit(ticker, signal_date, exit_price, exit_reason)
        if not success:
            return _error(f"{ticker} {signal_date} 시그널 없음", 404)
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"[/signals/exit] {e}")
        return _error(str(e))


@common_bp.route("/signals/open")
def open_signals():
    """GET /api/signals/open - 미청산 시그널 조회"""
    try:
        import signal_tracker
        df = signal_tracker.get_open_signals()
        return jsonify({"signals": df.to_dict(orient="records"), "count": len(df)})
    except Exception as e:
        logger.error(f"[/signals/open] {e}")
        return _error(str(e))


# ─────────────────────────────────────────
# 캐시 관리
# ─────────────────────────────────────────

@common_bp.route("/cache/clear", methods=["POST"])
def clear_cache():
    """POST /api/cache/clear - 전체 캐시 초기화"""
    try:
        from app.utils.cache import market_gate_cache, signal_cache, chart_cache
        market_gate_cache.clear()
        signal_cache.clear()
        chart_cache.clear()
        return jsonify({"success": True, "message": "캐시 초기화 완료"})
    except Exception as e:
        return _error(str(e))


# ─────────────────────────────────────────
# 설정 조회
# ─────────────────────────────────────────

@common_bp.route("/config")
def config():
    """GET /api/config - 현재 SignalConfig 설정값 조회"""
    try:
        from engine.config import SignalConfig
        cfg = SignalConfig()
        return jsonify({
            "min_trading_value": cfg.min_trading_value,
            "max_change_pct": cfg.max_change_pct,
            "stop_loss_pct": cfg.stop_loss_pct,
            "take_profit_pct": cfg.take_profit_pct,
            "r_ratio": cfg.r_ratio,
        })
    except Exception as e:
        return _error(str(e))
