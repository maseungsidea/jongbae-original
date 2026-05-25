"""
자동 스케줄러 (scheduler.py)

장 시작/종료 시 자동으로 데이터를 업데이트하고 VCP 스캔을 실행합니다.

실행 모드:
  python scheduler.py         → 주기적 스케줄 모드
  python scheduler.py --now   → 즉시 1회 실행 후 종료

스케줄:
  08:50 - 장 전 데이터 업데이트 (전일 데이터)
  14:50 - VCP 스캔 (인트라데이 기준, 휴장일 자동 스킵)
  14:55 - 전략 A/B 시그널 추적 (당일 종가 진입 / 익일 시초가 진입)
  15:00 - 일일 추천종목 텔레그램 발송

전략 분리:
  A (close)     : signals_log_A_close.csv     — 당일 종가 진입 (sw_pe_t8 계열)
  B (next_open) : signals_log_B_next_open.csv — 익일 시초가 진입, 갭 1% 필터
  legacy        : signals_log.csv             — 하위호환 (전략 A 와 동일 시그널)
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import time
from datetime import date

logger = logging.getLogger(__name__)


def _is_trading_day() -> bool:
    """오늘이 거래일인지 확인. 휴장이면 False."""
    try:
        from engine.market_utils import is_trading_day
        return is_trading_day()
    except Exception as e:
        logger.warning(f"[Scheduler] 거래일 확인 실패 ({e}) → 진행")
        return True


def run_ocf_check() -> dict:
    """08:30 실행 — 오버나이트 컨텍스트 필터 (Phase 1: advisory only).

    WARNING/DANGER 감지 시 텔레그램 경보 발송.
    결과를 data/ocf_latest.json 에 저장 (backtest_with_ocf.py 참조용).
    """
    if not _is_trading_day():
        logger.info("[Scheduler] 휴장일 — OCF 체크 스킵")
        return {"skipped": True}

    try:
        import json
        from pathlib import Path
        from engine.ocf import run_ocf
        from utils import notifier

        result = run_ocf()

        out = {
            "date": result.date.isoformat(),
            "severity": result.severity,
            "summary": result.summary,
            "flags": [
                {
                    "name": fl.name,
                    "triggered": fl.triggered,
                    "value": fl.value,
                    "threshold": fl.threshold,
                    "message": fl.message,
                }
                for fl in result.flags
            ],
        }
        Path("data").mkdir(exist_ok=True)
        with open("data/ocf_latest.json", "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)

        if result.severity in ("WARNING", "DANGER"):
            notifier.notify_ocf_alert(result)

        logger.info(f"[Scheduler] OCF 완료: {result.severity} — {result.summary}")
        return {"severity": result.severity, "summary": result.summary}

    except Exception as e:
        logger.error(f"[Scheduler] OCF 오류: {e}")
        return {"error": str(e)}


def run_vcp_scan() -> dict:
    """
    VCP 스캔을 실행하고 결과를 JSON으로 저장합니다.
    휴장일에는 자동 스킵됩니다.

    시그널은 세 곳에 동시 저장:
      - signals_log_A_close.csv     (전략 A)
      - signals_log_B_next_open.csv (전략 B)
      - signals_log.csv             (하위호환 legacy)
    """
    if not _is_trading_day():
        msg = "휴장일 — VCP 스캔 스킵"
        logger.info(f"[Scheduler] {msg}")
        return {"success": False, "message": msg, "skipped": True}

    logger.info("[Scheduler] VCP 스캔 시작")
    try:
        import signal_tracker
        from engine.generator import run_screener, save_result_to_json

        result = asyncio.run(run_screener(capital=50_000_000))
        path = save_result_to_json(result)

        # 전략 A (close), 전략 B (next_open), legacy 세 곳 저장
        saved_a = signal_tracker.persist_screener_result(
            result, log_path=signal_tracker.SIGNAL_LOG_CLOSE_PATH
        )
        saved_b = signal_tracker.persist_screener_result(
            result, log_path=signal_tracker.SIGNAL_LOG_NEXT_OPEN_PATH
        )
        saved_legacy = signal_tracker.persist_screener_result(result)  # legacy

        msg = (
            f"VCP 스캔 완료: {len(result.signals)}개 시그널 → {path} "
            f"(A:{saved_a} B:{saved_b} legacy:{saved_legacy})"
        )
        logger.info(f"[Scheduler] {msg}")
        return {
            "success": True, "message": msg,
            "signal_count": len(result.signals),
            "tracked_a": saved_a, "tracked_b": saved_b,
        }
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
    """장 마감 전 미청산 시그널 손절/익절 자동 기록.

    전략 A (close)    : signals_log_A_close.csv, entry_timing="close"
    전략 B (next_open): signals_log_B_next_open.csv, entry_timing="next_open", gap=1%
    """
    if not _is_trading_day():
        logger.info("[Scheduler] 휴장일 — 시그널 추적 스킵")
        return

    try:
        import signal_tracker
        from engine.config import SignalConfig

        cfg = SignalConfig()

        # 전략 A — 당일 종가 진입
        signal_tracker.track_signals(
            atr_period=cfg.atr_period,
            atr_multiplier=cfg.atr_multiplier,
            max_hold_days=cfg.max_hold_days,
            partial_exit_enabled=cfg.partial_exit_enabled,
            partial_exit_target_pct=cfg.partial_exit_target_pct,
            partial_exit_ratio=cfg.partial_exit_ratio,
            entry_timing="close",
            max_gap_pct=cfg.max_gap_pct,
            hard_stop_floor_pct=cfg.hard_stop_floor_pct,
            rsi_overbought_exit_enabled=cfg.rsi_overbought_exit_enabled,
            rsi_overbought_threshold=cfg.rsi_overbought_threshold,
            sanghan_exit_enabled=cfg.sanghan_exit_enabled,
            sanghan_threshold_pct=cfg.sanghan_threshold_pct,
            log_path=signal_tracker.SIGNAL_LOG_CLOSE_PATH,
        )
        logger.info("[Scheduler] 전략 A 추적 완료 (close)")

        # 전략 B — 익일 시초가 진입, 갭 1% 필터
        signal_tracker.track_signals(
            atr_period=cfg.atr_period,
            atr_multiplier=cfg.atr_multiplier,
            max_hold_days=cfg.max_hold_days,
            partial_exit_enabled=cfg.partial_exit_enabled,
            partial_exit_target_pct=cfg.partial_exit_target_pct,
            partial_exit_ratio=cfg.partial_exit_ratio,
            entry_timing="next_open",
            max_gap_pct=1.0,
            hard_stop_floor_pct=cfg.hard_stop_floor_pct,
            rsi_overbought_exit_enabled=cfg.rsi_overbought_exit_enabled,
            rsi_overbought_threshold=cfg.rsi_overbought_threshold,
            sanghan_exit_enabled=cfg.sanghan_exit_enabled,
            sanghan_threshold_pct=cfg.sanghan_threshold_pct,
            log_path=signal_tracker.SIGNAL_LOG_NEXT_OPEN_PATH,
        )
        logger.info("[Scheduler] 전략 B 추적 완료 (next_open, gap=1%)")

    except Exception as e:
        logger.error(f"[Scheduler] 시그널 추적 오류: {e}")


def run_daily_summary() -> None:
    """오늘 추천종목 슬림 요약본을 텔레그램으로 발송.

    `engine.generator.save_today_recommendations` 가 만든
    data/today_recommendations.json 을 읽어 단일 메시지로 전송.
    JONGGA_NOTIFY=0 또는 자격증명 부재 시 graceful no-op (notifier 가 가드).
    """
    if not _is_trading_day():
        logger.info("[Scheduler] 휴장일 — 일일 요약 스킵")
        return

    try:
        from utils import notifier
        sent = notifier.notify_today_recommendations()
        logger.info(f"[Scheduler] 일일 요약 발송 결과: {sent}")
    except Exception as e:
        logger.error(f"[Scheduler] 일일 요약 오류: {e}")


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
        run_ocf_check()
        run_full_update()
        run_vcp_scan()
        run_signal_tracking()
        run_daily_summary()
        return

    import schedule  # 주기 모드에서만 필요 (--now 시 미설치 환경도 동작)
    schedule.every().day.at("08:30").do(run_ocf_check)
    schedule.every().day.at("08:50").do(run_full_update)
    schedule.every().day.at("14:50").do(run_vcp_scan)
    schedule.every().day.at("14:55").do(run_signal_tracking)
    schedule.every().day.at("15:00").do(run_daily_summary)

    logger.info("[Scheduler] 스케줄 시작 (Ctrl+C 로 종료)")
    logger.info("  08:30 → OCF 오버나이트 리스크 체크")
    logger.info("  08:50 → 데이터 업데이트")
    logger.info("  14:50 → VCP 스캔 (휴장일 자동 스킵)")
    logger.info("  14:55 → 시그널 추적 [A:close / B:next_open]")
    logger.info("  15:00 → 일일 추천종목 텔레그램 발송")

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
