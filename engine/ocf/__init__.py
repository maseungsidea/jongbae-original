"""
Overnight Context Filter (engine/ocf/__init__.py)

전날 종가 ~ 익일 시초가 사이 발생하는 리스크 이벤트를 체크해
텔레그램 경보를 발송한다 (Phase 1: advisory only, 시그널 자동변경 없음).

체크 항목:
  1. S&P500 낙폭 (-1.5% 이하)
  2. VIX 급등 (25 이상 또는 +20%/일)
  3. EWY(미국상장 한국ETF) 야간 낙폭 (-1.5% 이하)
  4. DART 시스템 리스크 공시 (거래정지 등)
  5. 원/달러 환율 급등 (1520원 이상 또는 +1.5%/일)

EWY를 쓰는 이유:
  미국 거래소에서 거래되므로 전날 미국 마감 시점의 한국 시장 야간 센티먼트를
  반영. ^KS11(한국 현물 지수)은 당일 거래 시간 데이터라 look-ahead bias 발생.

Severity:
  OK      — 발동 플래그 0개
  WARNING — 발동 1~2개
  DANGER  — 발동 3개 이상
"""
from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class OCFConfig:
    sp500_drop_pct: float = -1.5
    vix_spike_abs: float = 25.0
    vix_spike_pct: float = 20.0
    ewy_drop_pct: float = -1.5          # EWY(한국 ETF) 야간 낙폭 임계
    usdkrw_abs: float = 1520.0          # 절대값 위기 기준 (2024-26 평균 1350~1480)
    usdkrw_spike_pct: float = 1.5       # 하루 +1.5% 급등 기준
    dart_risk_keywords: Tuple[str, ...] = (
        "거래정지", "매매거래정지", "시장조치",
        "긴급조치", "매매중단", "거래중단", "임시정지",
    )
    dart_lookback_days: int = 2         # DART 조회 기간 (당일 + 전일)
    warning_threshold: int = 1
    danger_threshold: int = 3
    enabled: bool = True


@dataclass
class OCFFlag:
    name: str
    triggered: bool
    value: float
    threshold: float
    message: str


@dataclass
class OCFResult:
    date: datetime.date
    severity: str               # "OK" | "WARNING" | "DANGER"
    flags: List[OCFFlag] = field(default_factory=list)
    summary: str = ""
    raw: dict = field(default_factory=dict)


def run_ocf(
    target_date: Optional[datetime.date] = None,
    config: Optional[OCFConfig] = None,
) -> OCFResult:
    """OCF 전체 체크 실행 후 OCFResult 반환.

    enabled=False 또는 환경에 따라 비활성 시 severity="OK" 로 즉시 반환.
    """
    if target_date is None:
        target_date = datetime.date.today()
    if config is None:
        config = OCFConfig()

    if not config.enabled:
        return OCFResult(date=target_date, severity="OK",
                         summary="OCF disabled")

    try:
        from engine.ocf.us_data import fetch_us_overnight
        from engine.ocf.checker import OvernightChecker

        us_data = fetch_us_overnight(as_of=target_date)
        checker = OvernightChecker(config=config)
        flags = checker.check_all(us_data=us_data, target_date=target_date)
        severity = checker.determine_severity(flags)
        summary = _build_summary(flags, severity)

        return OCFResult(
            date=target_date,
            severity=severity,
            flags=flags,
            summary=summary,
            raw=us_data,
        )
    except Exception as e:
        logger.error(f"[OCF] run_ocf 오류: {e}")
        return OCFResult(
            date=target_date,
            severity="OK",
            summary=f"OCF 체크 실패 (무시): {e}",
        )


def _build_summary(flags: List[OCFFlag], severity: str) -> str:
    triggered = [f for f in flags if f.triggered]
    if not triggered:
        return "오버나이트 리스크 이상 없음"
    items = " / ".join(f.name for f in triggered)
    return f"{severity}: {items} 경보 발동"
