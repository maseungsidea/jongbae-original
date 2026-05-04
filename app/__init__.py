"""
Flask 앱 팩토리 모듈.

create_app() 함수를 통해 Flask 인스턴스를 생성하고,
CORS 설정과 Blueprint 등록을 담당합니다.
"""
from flask import Flask, jsonify
from flask_cors import CORS

from app.routes import kr_bp, common_bp


def create_app() -> Flask:
    """
    Flask 앱 팩토리.
    Blueprint 등록, CORS 허용, Health check 엔드포인트를 설정합니다.
    """
    app = Flask(__name__)

    # 개발 환경에서 모든 출처 허용, 필요 시 origins 제한 가능
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # Blueprint 등록
    from app.routes.kr_market import kr_bp as _kr_bp
    from app.routes.common import common_bp as _common_bp
    app.register_blueprint(_kr_bp, url_prefix="/api/kr")
    app.register_blueprint(_common_bp, url_prefix="/api")

    @app.route("/api/health")
    def health_check():
        """서버 상태 확인 엔드포인트"""
        return jsonify({"status": "ok", "service": "closing-bet-api"})

    return app
