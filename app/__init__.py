"""
Flask 앱 팩토리 모듈.

create_app() 함수를 통해 Flask 인스턴스를 생성하고,
CORS 설정, Blueprint 등록, Next.js 정적 파일 서빙을 담당합니다.
"""
import os
from pathlib import Path

from flask import Flask, jsonify, send_file, send_from_directory
from flask_cors import CORS

ROOT = Path(__file__).resolve().parent.parent
FRONTEND_BUILD_DIR = ROOT / "frontend_build"


def create_app() -> Flask:
    """Flask 앱 팩토리."""
    app = Flask(__name__, static_folder=None)

    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # ── Blueprint 등록 ──────────────────────────────────────
    from app.routes.kr_market import kr_bp
    from app.routes.common import common_bp
    from app.routes.ocf import ocf_bp
    from app.routes.admin import admin_bp
    from app.routes.backtest import backtest_bp

    app.register_blueprint(kr_bp,       url_prefix="/api/kr")
    app.register_blueprint(common_bp,   url_prefix="/api")
    app.register_blueprint(ocf_bp,      url_prefix="/api/ocf")
    app.register_blueprint(admin_bp,    url_prefix="/api/admin")
    app.register_blueprint(backtest_bp, url_prefix="/api/kr/backtest")

    # ── 시그널 히스토리 엔드포인트 (kr_market.py 확장) ──────────
    @kr_bp.route("/signals/history")
    def signals_history():
        """GET /api/kr/signals/history?page=1&strategy=&status="""
        from flask import request
        import signal_tracker

        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 20))
        strategy = request.args.get("strategy", "")  # "A" | "B" | ""
        status_filter = request.args.get("status", "")  # "open" | "closed" | ""

        log_path = None
        if strategy == "A":
            log_path = signal_tracker.SIGNAL_LOG_CLOSE_PATH
        elif strategy == "B":
            log_path = signal_tracker.SIGNAL_LOG_NEXT_OPEN_PATH
        else:
            log_path = signal_tracker.SIGNAL_LOG_PATH

        df = signal_tracker._load(log_path)
        if not df.empty:
            if status_filter == "open":
                df = df[df["status"].isin(["pending", "entered"])]
            elif status_filter == "closed":
                df = df[df["status"].isin(["exited", "invalidated"])]
            df = df.sort_values("signal_date", ascending=False)

        total = len(df)
        start = (page - 1) * per_page
        page_df = df.iloc[start : start + per_page]

        return jsonify({
            "signals": page_df.fillna("").to_dict(orient="records"),
            "total": total,
            "page": page,
            "per_page": per_page,
        })

    # ── 헬스체크 ───────────────────────────────────────────
    @app.route("/api/health")
    def health_check():
        return jsonify({"status": "ok", "service": "closing-bet-api"})

    # ── Next.js 정적 파일 서빙 ──────────────────────────────
    # frontend_build/ 가 없으면 (로컬 개발 시) API 전용으로 동작
    if FRONTEND_BUILD_DIR.exists():
        @app.route("/", defaults={"path": ""})
        @app.route("/<path:path>")
        def serve_frontend(path: str):
            # 1) 정확한 파일이 있으면 그대로 서빙 (_next/static/*, favicon.ico 등)
            candidate = FRONTEND_BUILD_DIR / path
            if candidate.is_file():
                return send_from_directory(str(FRONTEND_BUILD_DIR), path)

            # 2) trailingSlash 옵션으로 생성된 index.html (예: dashboard/kr/index.html)
            index_html = FRONTEND_BUILD_DIR / path / "index.html"
            if index_html.is_file():
                return send_file(str(index_html))

            # 3) 루트 index.html (SPA 폴백)
            root_index = FRONTEND_BUILD_DIR / "index.html"
            if root_index.is_file():
                return send_file(str(root_index))

            return jsonify({"error": "Not Found"}), 404

    return app
