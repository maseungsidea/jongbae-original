"""
OCF 체크 항목 구현 (engine/ocf/checker.py)

OvernightChecker 클래스가 5개 체크를 실행하고 severity 를 판정한다.
각 체크는 독립적으로 실패해도 예외를 던지지 않고 triggered=False 로 반환한다.
"""
from __future__ import annotations

import datetime
import logging
import os
from typing import List, Optional

from engine.ocf import OCFConfig, OCFFlag

logger = logging.getLogger(__name__)


class OvernightChecker:
    def __init__(self, config: Optional[OCFConfig] = None):
        self.config = config or OCFConfig()

    def check_all(
        self,
        us_data: dict,
        target_date: Optional[datetime.date] = None,
    ) -> List[OCFFlag]:
        if target_date is None:
            target_date = datetime.date.today()
        return [
            self.check_sp500_drop(us_data),
            self.check_vix_spike(us_data),
            self.check_ewy_drop(us_data),
            self.check_dart_major(target_date),
            self.check_exchange_rate(us_data),
        ]

    def determine_severity(self, flags: List[OCFFlag]) -> str:
        n = sum(1 for f in flags if f.triggered)
        if n >= self.config.danger_threshold:
            return "DANGER"
        if n >= self.config.warning_threshold:
            return "WARNING"
        return "OK"

    # ── 개별 체크 ──────────────────────────────────────────────

    def check_sp500_drop(self, us_data: dict) -> OCFFlag:
        val = us_data.get("spy_chg_pct")
        thr = self.config.sp500_drop_pct
        if val is None:
            return OCFFlag("sp500_drop", False, 0.0, thr, "SPY 데이터 없음(스킵)")
        triggered = val <= thr
        msg = (
            f"S&P500(SPY) {val:+.2f}% — 임계 {thr:+.1f}% 이하 경보"
            if triggered
            else f"S&P500(SPY) {val:+.2f}% — 정상"
        )
        return OCFFlag("sp500_drop", triggered, round(val, 2), thr, msg)

    def check_vix_spike(self, us_data: dict) -> OCFFlag:
        vix_abs = us_data.get("vix_close")
        vix_chg = us_data.get("vix_chg_pct")
        thr_abs = self.config.vix_spike_abs
        thr_pct = self.config.vix_spike_pct

        if vix_abs is None:
            return OCFFlag("vix_spike", False, 0.0, thr_abs, "VIX 데이터 없음(스킵)")

        triggered_abs = vix_abs >= thr_abs
        triggered_pct = (vix_chg is not None) and (vix_chg >= thr_pct)
        triggered = triggered_abs or triggered_pct

        if triggered_abs:
            msg = f"VIX {vix_abs:.1f} — 공포 임계 {thr_abs:.0f} 초과"
        elif triggered_pct:
            msg = f"VIX 급등 {vix_chg:+.1f}% — 임계 +{thr_pct:.0f}% 초과"
        else:
            msg = f"VIX {vix_abs:.1f} — 정상"

        return OCFFlag("vix_spike", triggered, round(vix_abs, 1), thr_abs, msg)

    def check_ewy_drop(self, us_data: dict) -> OCFFlag:
        """EWY(미국상장 한국ETF) 야간 낙폭 체크.

        ^KS11(한국 현물) 대신 EWY를 사용하는 이유:
        EWY는 미국 거래 시간(전날 16:00 ET ≈ 06:00 KST)에 마감하므로
        순수 오버나이트 한국 시장 센티먼트를 반영한다. look-ahead bias 없음.
        """
        val = us_data.get("ewy_chg_pct")
        thr = self.config.ewy_drop_pct
        if val is None:
            return OCFFlag("ewy_drop", False, 0.0, thr,
                           "EWY(한국ETF) 데이터 없음(스킵)")
        triggered = val <= thr
        msg = (
            f"EWY(한국ETF) {val:+.2f}% — 임계 {thr:+.1f}% 이하 경보"
            if triggered
            else f"EWY(한국ETF) {val:+.2f}% — 정상"
        )
        return OCFFlag("ewy_drop", triggered, round(val, 2), thr, msg)

    def check_dart_major(self, target_date: datetime.date) -> OCFFlag:
        """DART 시스템 리스크 공시 체크.

        target_date 당일 + 전일(lookback_days)을 조회해 야간 공시도 포착.
        """
        dart_key = os.environ.get("DART_API_KEY", "").strip()
        if not dart_key:
            return OCFFlag("dart_major", False, 0.0, 0.0, "DART_API_KEY 미설정(스킵)")

        keywords = self.config.dart_risk_keywords

        try:
            import OpenDartReader  # type: ignore
            api = OpenDartReader(dart_key)

            # 전일~당일 범위 (야간 공시 포착)
            lookback = self.config.dart_lookback_days
            start_date = target_date - datetime.timedelta(days=lookback - 1)
            start_str = start_date.strftime("%Y%m%d")
            end_str = target_date.strftime("%Y%m%d")

            df = api.list(start=start_str, end=end_str)
            if df is not None and not df.empty and "report_nm" in df.columns:
                for kw in keywords:
                    if df["report_nm"].str.contains(kw, na=False).any():
                        return OCFFlag(
                            "dart_major", True, 1.0, 0.0,
                            f"DART 시스템 리스크 공시: '{kw}' 감지"
                        )
            return OCFFlag("dart_major", False, 0.0, 0.0, "DART 이상 공시 없음")
        except Exception as e:
            logger.warning(f"[OCF/checker] DART 체크 실패: {e}")
            return OCFFlag("dart_major", False, 0.0, 0.0,
                           f"DART 체크 오류(무시): {type(e).__name__}")

    def check_exchange_rate(self, us_data: dict) -> OCFFlag:
        val = us_data.get("usdkrw")
        chg = us_data.get("usdkrw_chg_pct")
        thr_abs = self.config.usdkrw_abs
        thr_pct = self.config.usdkrw_spike_pct

        if val is None:
            return OCFFlag("exchange_rate", False, 0.0, thr_abs,
                           "원/달러 데이터 없음(스킵)")

        triggered_abs = val >= thr_abs
        triggered_pct = (chg is not None) and (chg >= thr_pct)
        triggered = triggered_abs or triggered_pct

        if triggered_abs:
            msg = f"원/달러 {val:,.0f}원 — 위기 임계 {thr_abs:,.0f}원 초과"
        elif triggered_pct:
            msg = f"원/달러 급등 {chg:+.2f}% — 임계 +{thr_pct:.1f}% 초과"
        else:
            msg = f"원/달러 {val:,.0f}원 — 정상"

        return OCFFlag("exchange_rate", triggered, round(val, 0), thr_abs, msg)
