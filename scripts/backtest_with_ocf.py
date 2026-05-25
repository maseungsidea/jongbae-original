"""
OCF 적용 백테스트 비교 (scripts/backtest_with_ocf.py)

과거 SPY/VIX/KRW=X/^KS11 데이터로 OCF 플래그를 사전 계산한 뒤,
기존 백테 로직에서 WARNING/DANGER 날 시그널을 스킵했을 때 EV 변화를 측정한다.

실행:
    python3 scripts/backtest_with_ocf.py --label ocf_v1
    python3 scripts/backtest_with_ocf.py --label ocf_v1 --start 2024-01-01 --end 2025-12-31
    python3 scripts/backtest_with_ocf.py --label ocf_v1 --entry-timing next_open

출력:
    data/backtests/ocf_v1_comparison.json
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger(__name__)


def precompute_ocf_flags(
    start: str,
    end: str,
    config=None,  # type: OCFConfig | None
) -> dict[str, str]:
    """기간 내 각 거래일의 OCF severity 사전 계산.

    yfinance 로 SPY/VIX/EWY/KRW=X 과거 데이터를 일괄 다운로드해
    {날짜: "OK"/"WARNING"/"DANGER"} dict 반환.

    주의:
      - DART 공시는 과거 API 한계로 항상 False (triggered=False) 처리
      - EWY(미국상장 한국ETF) 사용 — look-ahead bias 없음
    """
    import warnings
    warnings.filterwarnings("ignore")

    try:
        import yfinance as yf
    except ImportError:
        logger.error("yfinance 설치 필요: pip install yfinance")
        return {}

    from engine.ocf import OCFConfig
    from engine.ocf.checker import OvernightChecker

    if config is None:
        config = OCFConfig()
    checker = OvernightChecker(config=config)

    logger.info(f"[OCF백테] 과거 데이터 다운로드: {start} ~ {end}")

    tickers_str = "SPY ^VIX EWY KRW=X"
    df = yf.download(tickers_str, start=start, end=end,
                     interval="1d", progress=False, auto_adjust=True)

    if df.empty:
        logger.error("[OCF백테] yfinance 데이터 없음")
        return {}

    closes = df["Close"] if isinstance(df.columns, pd.MultiIndex) else df[["Close"]]

    def _pct(col: str):
        if col not in closes.columns:
            return pd.Series(dtype=float)
        s = closes[col].dropna()
        return s.pct_change() * 100

    spy_chg = _pct("SPY")
    vix_close = closes.get("^VIX", pd.Series(dtype=float)).dropna()
    vix_chg = _pct("^VIX")
    ewy_chg = _pct("EWY")   # iShares MSCI South Korea ETF — look-ahead bias 없음
    usdkrw = closes.get("KRW=X", pd.Series(dtype=float)).dropna()
    usdkrw_chg = _pct("KRW=X")

    flags_by_date: dict[str, str] = {}
    all_dates = closes.index

    try:
        for dt in all_dates:
            dt_str = pd.Timestamp(dt).strftime("%Y-%m-%d")

            def _get(series: pd.Series, default=None):
                try:
                    v = series.get(dt)
                    return float(v) if v is not None and not pd.isna(v) else default
                except Exception:
                    return default

            us_data = {
                "spy_chg_pct": _get(spy_chg),
                "vix_close": _get(vix_close),
                "vix_chg_pct": _get(vix_chg),
                "ewy_chg_pct": _get(ewy_chg),
                "usdkrw": _get(usdkrw),
                "usdkrw_chg_pct": _get(usdkrw_chg),
            }

            # DART 과거 체크 생략 (API 한계)
            from engine.ocf import OCFFlag
            flags = checker.check_all(us_data=us_data, target_date=pd.Timestamp(dt).date())
            # DART flag 를 항상 OK 로 덮어씌움 (과거 백테 한계 명시)
            flags = [f if f.name != "dart_major" else
                     OCFFlag("dart_major", False, 0.0, 0.0, "백테: DART 생략")
                     for f in flags]

            severity = checker.determine_severity(flags)
            flags_by_date[dt_str] = severity
    except Exception as e:
        logger.error(f"[OCF백테] 플래그 계산 중 오류 (처리된 날짜: {len(flags_by_date)}): {e}")
        return flags_by_date

    logger.info(f"[OCF백테] {len(flags_by_date)}일 플래그 계산 완료")
    return flags_by_date


def run_comparison(
    backtest_json: str,
    flags_by_date: dict[str, str],
) -> dict:
    """기존 백테 결과 JSON + OCF 플래그로 3가지 시나리오 비교."""
    with open(backtest_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    all_trades = data["trades"]
    label = data.get("label", "unknown")

    def _stats(trades: list) -> dict:
        if not trades:
            return {"trades": 0, "ev_pct": 0.0, "wr": 0.0, "mdd": 0.0}
        n = len(trades)
        nets = [t["net"] for t in trades]
        wins = sum(1 for x in nets if x > 0)
        ev = sum(nets) / n * 100
        wr = wins / n

        # MDD 계산
        cum = 0.0
        peak = 0.0
        max_dd = 0.0
        for net in nets:
            cum += net
            peak = max(peak, cum)
            max_dd = min(max_dd, cum - peak)

        return {
            "trades": n,
            "ev_pct": round(ev, 3),
            "wr": round(wr, 3),
            "mdd_pct": round(max_dd * 100, 2),
        }

    baseline_trades = all_trades
    ocf_warning_trades = [
        t for t in all_trades
        if flags_by_date.get(t["entry_date"], "OK") == "OK"
    ]
    trades_excluding_danger = [
        t for t in all_trades
        if flags_by_date.get(t["entry_date"], "OK") not in ("DANGER",)
    ]

    n_total = len(all_trades)
    n_warning_filtered = n_total - len(ocf_warning_trades)
    n_danger_filtered = n_total - len(trades_excluding_danger)

    # 날짜별 severity 카운트
    severity_counts: dict[str, int] = {"OK": 0, "WARNING": 0, "DANGER": 0}
    for v in flags_by_date.values():
        severity_counts[v] = severity_counts.get(v, 0) + 1

    return {
        "label": label,
        "baseline": _stats(baseline_trades),
        "with_ocf_warning": {
            **_stats(ocf_warning_trades),
            "filter_rate": round(n_warning_filtered / n_total, 3) if n_total else 0,
            "filtered_trades": n_warning_filtered,
        },
        "with_ocf_danger_only": {
            **_stats(trades_excluding_danger),
            "filter_rate": round(n_danger_filtered / n_total, 3) if n_total else 0,
            "filtered_trades": n_danger_filtered,
        },
        "ocf_flag_days": severity_counts,
        "goal_met": {
            "baseline_ev_2pct": _stats(baseline_trades)["ev_pct"] >= 2.0,
            "ocf_warning_ev_2pct": _stats(ocf_warning_trades)["ev_pct"] >= 2.0,
            "filter_rate_ok": round(n_warning_filtered / n_total, 3) <= 0.30 if n_total else True,
        },
    }


def main():
    parser = argparse.ArgumentParser(description="OCF 적용 백테스트 비교")
    parser.add_argument("--label", default="sw_pe_t8",
                        help="비교할 기존 백테 레이블 (data/backtests/<label>.json)")
    parser.add_argument("--start", default="2024-01-01", help="OCF 기간 시작")
    parser.add_argument("--end", default="2026-04-30", help="OCF 기간 종료")
    args = parser.parse_args()

    bt_path = ROOT / "data" / "backtests" / f"{args.label}.json"
    if not bt_path.exists():
        logger.error(f"백테 파일 없음: {bt_path}")
        sys.exit(1)

    flags = precompute_ocf_flags(args.start, args.end)
    if not flags:
        logger.error("OCF 플래그 계산 실패")
        sys.exit(1)

    result = run_comparison(str(bt_path), flags)

    out_path = ROOT / "data" / "backtests" / f"{args.label}_ocf_comparison.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    logger.info(f"[OCF백테] 결과 저장: {out_path}")

    # 콘솔 요약
    b = result["baseline"]
    w = result["with_ocf_warning"]
    d = result["with_ocf_danger_only"]
    print(f"\n{'='*60}")
    print(f"  백테 레이블: {args.label}")
    print(f"{'='*60}")
    print(f"  {'시나리오':<22} {'n':>5}  {'EV%':>7}  {'WR':>6}  {'MDD%':>7}  {'filter':>7}")
    print(f"  {'-'*58}")
    print(f"  {'baseline (OCF없음)':<22} {b['trades']:>5}  {b['ev_pct']:>+7.3f}  {b['wr']:>6.1%}  {b['mdd_pct']:>7.2f}%")
    print(f"  {'OCF WARNING 이상 스킵':<22} {w['trades']:>5}  {w['ev_pct']:>+7.3f}  {w['wr']:>6.1%}  {w['mdd_pct']:>7.2f}%  {w['filter_rate']:>6.1%}")
    print(f"  {'OCF DANGER만 스킵':<22} {d['trades']:>5}  {d['ev_pct']:>+7.3f}  {d['wr']:>6.1%}  {d['mdd_pct']:>7.2f}%  {d['filter_rate']:>6.1%}")
    print(f"\n  OCF 날짜별 분포: {result['ocf_flag_days']}")
    print(f"\n  ✅ Phase 2 자동화 조건 체크:")
    g = result["goal_met"]
    print(f"     baseline EV ≥ 2%:        {'✅' if g['baseline_ev_2pct'] else '❌'}")
    print(f"     OCF_warning EV ≥ 2%:     {'✅' if g['ocf_warning_ev_2pct'] else '❌'}")
    print(f"     filter_rate ≤ 30%:       {'✅' if g['filter_rate_ok'] else '❌'}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
