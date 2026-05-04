"""
자동 스케줄러 (scheduler.py)

장 시작/종료 시 자동으로 데이터를 업데이트하고 VCP 스캔을 실행합니다.

실행 모드:
  python scheduler.py         → 주기적 스케줄 모드
  python scheduler.py --now   → 즉시 1회 실행 후 종료

스케줄:
  08:50 - 장 전 데이터 업데이트 (전일 데이터)
  15:35 - 장 마감 후 VCP 스캔
  15:40 - 시그널 추적 (손절/익절 자동 기록)
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import time
from datetime import date

import schedule

logger = logging.getLogger(__name__)


def run_vcp_scan() -> dict:
    """
    VCP 스캔을 실행하고 결과를 JSON으로 저장합니다.
    app/routes/kr_market.py 의 /vcp-scan 엔드포인트와 동일한 로직입니다.
    """
    logger.info("[Scheduler] VCP 스캔 시작")
    try:
        from engine.generator import run_screener, save_result_to_json
        result = asyncio.run(run_screener(capital=50_000_000))
        path = save_result_to_json(result)
        msg = f"VCP 스캔 완료: {len(result.signals)}개 시그널 → {path}"
        logger.info(f"[Scheduler] {msg}")
        return {"success": True, "message": msg, "signal_count": len(result.signals)}
    except Exception as e:
        logger.error(f"[Scheduler] VCP 스캔 오류: {e}")
        return {"success": False, "error": str(e)}


def run_full_update() -> dict:
    """
    전체 데이터 업데이트를 실행합니다.
    1. 일봉 데이터 증분 업데이트
    2. 수급 데이터 업데이트

    /api/kr/update 엔드포인트에서도 이 함수를 호출합니다.
    """
    logger.info("[Scheduler] 전체 데이터 업데이트 시작")
    results = {}

    # 일봉 데이터 업데이트
    try:
        import subprocess, sys
        proc = subprocess.run(
            [sys.executable, "scripts/create_complete_daily_prices.py"],
            capture_output=True, text=True, timeout=600
        )
        results["daily_prices"] = {
            "success": proc.returncode == 0,
            "output": proc.stdout[-500:] if proc.stdout else "",
        }
    except Exception as e:
        results["daily_prices"] = {"success": False, "error": str(e)}

    # 수급 데이터 업데이트
    try:
        import subprocess, sys
        proc = subprocess.run(
            [sys.executable, "all_institutional_trend_data.py"],
            capture_output=True, text=True, timeout=600
        )
        results["supply_data"] = {
            "success": proc.returncode == 0,
            "output": proc.stdout[-500:] if proc.stdout else "",
        }
    except Exception as e:
        results["supply_data"] = {"success": False, "error": str(e)}

    logger.info(f"[Scheduler] 업데이트 완료: {results}")
    return results


def run_signal_tracking() -> None:
    """장 마감 후 미청산 시그널 손절/익절 자동 기록"""
    try:
        import signal_tracker
        signal_tracker.track_signals()
    except Exception as e:
        logger.error(f"[Scheduler] 시그널 추적 오류: {e}")


def main() -> None:
    """
    스케줄러 메인 진입점.
    --now 플래그 시 즉시 1회 실행 후 종료.
    """
    parser = argparse.ArgumentParser(description="종가배팅 스케줄러")
    parser.add_argument("--now", action="store_true", help="즉시 1회 실행 후 종료")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if args.now:
        logger.info("[Scheduler] 즉시 실행 모드")
        run_full_update()
        run_vcp_scan()
        run_signal_tracking()
        return

    # 주기적 스케줄 등록
    schedule.every().day.at("08:50").do(run_full_update)
    schedule.every().day.at("15:35").do(run_vcp_scan)
    schedule.every().day.at("15:40").do(run_signal_tracking)

    logger.info("[Scheduler] 스케줄 시작 (Ctrl+C 로 종료)")
    logger.info("  08:50 → 데이터 업데이트")
    logger.info("  15:35 → VCP 스캔")
    logger.info("  15:40 → 시그널 추적")

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
