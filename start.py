"""
통합 진입점 (start.py)

Flask 웹 서버(API + 프론트엔드 정적 파일)와
스케줄러를 단일 프로세스에서 실행한다.

Railway 배포: 이 파일이 CMD 로 실행됨.
로컬 개발: python start.py (또는 flask_app.py 따로 + scheduler.py 따로)
"""
from __future__ import annotations

import logging
import os
import threading
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def _run_scheduler() -> None:
    import schedule
    from scheduler import (
        run_ocf_check,
        run_full_update,
        run_vcp_scan,
        run_signal_tracking,
        run_daily_summary,
    )

    try:
        from hub_client import HubClient as _HubClient
        _hub = _HubClient("jongbae-original")
    except Exception:
        _hub = None

    def _send_heartbeat():
        if _hub:
            try:
                _hub.push_heartbeat()
            except Exception:
                pass

    schedule.every().day.at("08:30").do(run_ocf_check)
    schedule.every().day.at("08:50").do(run_full_update)
    schedule.every().day.at("14:50").do(run_vcp_scan)
    schedule.every().day.at("14:55").do(run_signal_tracking)
    schedule.every().day.at("15:00").do(run_daily_summary)
    schedule.every(5).minutes.do(_send_heartbeat)

    logger.info("[Start] 스케줄러 스레드 시작 (08:30/08:50/14:50/14:55/15:00 KST + 5분 heartbeat)")
    _send_heartbeat()  # 즉시 1회 전송
    while True:
        schedule.run_pending()
        time.sleep(30)


# 스케줄러를 데몬 스레드로 백그라운드 실행
_scheduler_thread = threading.Thread(
    target=_run_scheduler, daemon=True, name="scheduler"
)
_scheduler_thread.start()

# Flask 앱 기동 (메인 스레드)
try:
    from flask_app import app as flask_app  # noqa: E402
except Exception as _startup_err:
    # 기동 실패 시 hub에 즉시 알림 후 재raise (Railway ON_FAILURE 재시작 유지)
    try:
        from hub_client import HubClient as _hc
        _hc("jongbae-original").push_error(f"Flask startup failed: {_startup_err}")
    except Exception:
        pass
    logger.critical(f"[Start] Flask 기동 실패: {_startup_err}")
    raise

port = int(os.environ.get("PORT", 5001))
logger.info(f"[Start] Flask 서버 시작: 0.0.0.0:{port}")
flask_app.run(host="0.0.0.0", port=port, use_reloader=False, threaded=True)
