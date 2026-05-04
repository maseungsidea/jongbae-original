"""
Flask 서버 진입점.
`python flask_app.py` 명령으로 개발 서버를 시작합니다.
프로덕션에서는 gunicorn flask_app:app 으로 실행하세요.
"""
import os
from dotenv import load_dotenv
from app import create_app

load_dotenv()

app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("FLASK_PORT", 5001))
    debug = os.getenv("FLASK_ENV", "development") == "development"
    print(f"[START] 종가배팅 API 서버 시작: http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=debug)
