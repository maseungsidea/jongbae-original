"""
KR 마켓 API Blueprint (app/routes/kr_market.py)

/api/kr/ 하위 엔드포인트를 구현합니다.
총 22개 엔드포인트를 제공하며, 캐시·비동기 엔진과 연동됩니다.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import date
from pathlib import Path

from flask import Blueprint, jsonify, request

from app.utils.cache import market_gate_cache, signal_cache, chart_cache

kr_bp = Blueprint("kr_market", __name__)
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT / "data"


# ─────────────────────────────────────────
# 유틸 함수
# ─────────────────────────────────────────

def _error(msg: str, status: int = 500):
    return jsonify({"error": msg}), status


def _run_async(coro):
    """Flask 동기 컨텍스트에서 비동기 함수를 실행합니다."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


# ─────────────────────────────────────────
# 시장 상태
# ─────────────────────────────────────────

@kr_bp.route("/market-status")
def market_status():
    """
    GET /api/kr/market-status
    MA200 기반 시장 상태 (MarketGate 결과)
    """
    cached = market_gate_cache.get("market_status")
    if cached:
        return jsonify(cached)

    try:
        from market_gate import run_kr_market_gate
        result = run_kr_market_gate()
        data = result.to_dict()
        market_gate_cache.set("market_status", data)
        return jsonify(data)
    except Exception as e:
        logger.error(f"[/market-status] {e}")
        return _error(str(e))


@kr_bp.route("/market-gate")
def market_gate():
    """
    GET /api/kr/market-gate
    Market Gate (GREEN/YELLOW/RED) 상태 조회 (캐시 공유)
    """
    return market_status()


# ─────────────────────────────────────────
# VCP 시그널
# ─────────────────────────────────────────

@kr_bp.route("/signals")
def signals():
    """
    GET /api/kr/signals
    VCP + 수급 시그널 목록 (캐시: 5분)
    """
    cached = signal_cache.get("signals")
    if cached:
        return jsonify(cached)

    try:
        from screener import SmartMoneyScreener
        screener = SmartMoneyScreener()
        results = screener.run_screening(max_stocks=50)
        data = screener.generate_signals(results)
        signal_cache.set("signals", {"signals": data, "count": len(data)})
        return jsonify({"signals": data, "count": len(data)})
    except Exception as e:
        logger.error(f"[/signals] {e}")
        return _error(str(e))


@kr_bp.route("/signals/today")
def signals_today():
    """
    GET /api/kr/signals/today
    당일 생성된 시그널 조회
    """
    try:
        import signal_tracker
        df = signal_tracker.get_today_signals()
        return jsonify({"signals": df.to_dict(orient="records"), "count": len(df)})
    except Exception as e:
        logger.error(f"[/signals/today] {e}")
        return _error(str(e))


# ─────────────────────────────────────────
# VCP 스캔 (온디맨드)
# ─────────────────────────────────────────

@kr_bp.route("/vcp-scan", methods=["POST"])
def vcp_scan():
    """
    POST /api/kr/vcp-scan
    VCP 스캔 수동 실행 (실시간 엔진 사용)

    Body (JSON, optional):
    {
      "capital": 50000000,
      "markets": ["KOSPI", "KOSDAQ"],
      "top_n": 30
    }
    """
    body = request.get_json(silent=True) or {}
    capital = float(body.get("capital", 50_000_000))
    markets = body.get("markets", ["KOSPI", "KOSDAQ"])
    top_n = int(body.get("top_n", 30))

    try:
        from engine.generator import run_screener, save_result_to_json
        result = _run_async(run_screener(capital=capital, markets=markets, top_n=top_n))

        # JSON 파일 저장 후 캐시 초기화
        save_result_to_json(result)
        signal_cache.delete("signals")

        return jsonify(result.to_dict())
    except Exception as e:
        logger.error(f"[/vcp-scan] {e}")
        return _error(str(e))


# ─────────────────────────────────────────
# AI 분석
# ─────────────────────────────────────────

@kr_bp.route("/ai-summary/<ticker>")
def ai_summary(ticker: str):
    """
    GET /api/kr/ai-summary/<ticker>
    단일 종목 AI 분석 + 뉴스 감성 점수
    """
    cache_key = f"ai_summary_{ticker}"
    cached = signal_cache.get(cache_key)
    if cached:
        return jsonify(cached)

    try:
        from engine.generator import analyze_single_stock_by_code
        signal = _run_async(analyze_single_stock_by_code(ticker))

        if signal is None:
            return _error(f"{ticker} 분석 실패 (Grade C 또는 데이터 없음)", 404)

        data = signal.to_dict()
        signal_cache.set(cache_key, data, ttl=300)
        return jsonify(data)
    except Exception as e:
        logger.error(f"[/ai-summary/{ticker}] {e}")
        return _error(str(e))


@kr_bp.route("/ai-analysis")
def ai_analysis():
    """
    GET /api/kr/ai-analysis
    최신 AI 분석 전체 (jongga_v2_latest.json)
    """
    json_path = DATA_DIR / "jongga_v2_latest.json"
    if not json_path.exists():
        return _error("분석 결과 파일 없음. /vcp-scan 을 먼저 실행하세요.", 404)

    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
    return jsonify(data)


@kr_bp.route("/ai-history-dates")
def ai_history_dates():
    """
    GET /api/kr/ai-history-dates
    AI 분석 히스토리 날짜 목록
    """
    try:
        files = sorted(DATA_DIR.glob("jongga_v2_*.json"))
        dates = [f.stem.replace("jongga_v2_", "") for f in files if f.stem != "jongga_v2_latest"]
        return jsonify({"dates": dates})
    except Exception as e:
        return _error(str(e))


@kr_bp.route("/ai-history/<hist_date>")
def ai_history(hist_date: str):
    """
    GET /api/kr/ai-history/<date>
    특정 날짜 AI 분석 결과
    """
    path = DATA_DIR / f"jongga_v2_{hist_date}.json"
    if not path.exists():
        return _error(f"{hist_date} 데이터 없음", 404)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return jsonify(data)


# ─────────────────────────────────────────
# 종목 차트
# ─────────────────────────────────────────

@kr_bp.route("/stock-chart/<ticker>")
def stock_chart(ticker: str):
    """
    GET /api/kr/stock-chart/<ticker>?days=90
    종목 일봉 OHLCV 데이터
    """
    days = int(request.args.get("days", 90))
    cache_key = f"chart_{ticker}_{days}"
    cached = chart_cache.get(cache_key)
    if cached:
        return jsonify(cached)

    try:
        from engine.collectors import KRXCollector
        from engine.config import SignalConfig

        async def _fetch():
            async with KRXCollector(SignalConfig()) as c:
                return await c.get_chart_data(ticker, days=days)

        charts = _run_async(_fetch())
        data = [
            {
                "date": c.date, "open": c.open, "high": c.high,
                "low": c.low, "close": c.close, "volume": c.volume
            }
            for c in charts
        ]
        chart_cache.set(cache_key, {"ticker": ticker, "data": data})
        return jsonify({"ticker": ticker, "data": data})
    except Exception as e:
        logger.error(f"[/stock-chart/{ticker}] {e}")
        return _error(str(e))


# ─────────────────────────────────────────
# 시그널 히스토리
# ─────────────────────────────────────────

@kr_bp.route("/signals/history")
def signals_history():
    """GET /api/kr/signals/history?page=1&strategy=A|B&status=open|closed"""
    import signal_tracker

    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 20))
    strategy = request.args.get("strategy", "")
    status_filter = request.args.get("status", "")

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
    page_df = df.iloc[start: start + per_page]

    return jsonify({
        "signals": page_df.fillna("").to_dict(orient="records"),
        "total": total,
        "page": page,
        "per_page": per_page,
    })


# ─────────────────────────────────────────
# 성과 및 수익률
# ─────────────────────────────────────────

@kr_bp.route("/performance")
def performance():
    """
    GET /api/kr/performance
    전체 시그널 성과 통계 (신호 로그 기반)
    """
    try:
        import signal_tracker
        df = signal_tracker._load()
        if df.empty:
            return jsonify({"total": 0, "win_rate": 0, "avg_return": 0})

        closed = df[df["status"] == "exited"]
        total = len(closed)
        wins = len(closed[closed["return_pct"] > 0])
        avg_return = float(closed["return_pct"].mean()) if total > 0 else 0

        return jsonify({
            "total": total,
            "win_rate": round(wins / total * 100, 1) if total > 0 else 0,
            "avg_return": round(avg_return, 2),
            "by_reason": closed["exit_reason"].value_counts().to_dict() if total > 0 else {},
        })
    except Exception as e:
        logger.error(f"[/performance] {e}")
        return _error(str(e))


@kr_bp.route("/cumulative-return")
def cumulative_return():
    """
    GET /api/kr/cumulative-return
    누적 수익률 시계열 데이터 (charts용)
    """
    try:
        import signal_tracker
        df = signal_tracker._load()
        if df.empty:
            return jsonify({"data": []})

        closed = df[df["status"] == "exited"].copy()
        if closed.empty:
            return jsonify({"data": []})

        closed = closed.sort_values("exit_date")
        closed["cumulative_pnl"] = closed["pnl"].fillna(0).cumsum()
        data = closed[["exit_date", "cumulative_pnl"]].dropna().to_dict(orient="records")
        return jsonify({"data": data})
    except Exception as e:
        logger.error(f"[/cumulative-return] {e}")
        return _error(str(e))


# ─────────────────────────────────────────
# 업데이트 (데이터 갱신)
# ─────────────────────────────────────────

@kr_bp.route("/update", methods=["POST"])
def update():
    """
    POST /api/kr/update
    데이터 파일 갱신 (scheduler.run_full_update 호출)
    """
    try:
        from scheduler import run_full_update
        result = run_full_update()
        # 캐시 초기화
        market_gate_cache.clear()
        signal_cache.clear()
        chart_cache.clear()
        return jsonify(result)
    except Exception as e:
        logger.error(f"[/update] {e}")
        return _error(str(e))


# ─────────────────────────────────────────
# 페이퍼 트레이딩 계좌
# ─────────────────────────────────────────

@kr_bp.route("/paper-account")
def paper_account():
    """
    GET /api/kr/paper-account
    페이퍼 계좌 현황 (잔고·포지션·손익)
    """
    try:
        import paper_trading as pt
        summary = pt.get_summary()
        return jsonify(summary)
    except Exception as e:
        logger.error(f"[/paper-account] {e}")
        return _error(str(e))


@kr_bp.route("/paper-account/reset", methods=["POST"])
def paper_account_reset():
    """
    POST /api/kr/paper-account/reset
    페이퍼 계좌 초기화 (씨드머니 복구)
    """
    try:
        import paper_trading as pt
        acc = pt.reset_account()
        return jsonify({"ok": True, "seed": acc["seed"], "cash": acc["cash"]})
    except Exception as e:
        logger.error(f"[/paper-account/reset] {e}")
        return _error(str(e))


# ─────────────────────────────────────────
# 종가베팅 V2 (jongga-v2) 별칭 라우트
#
# api.ts의 closingBetAPI가 호출하는 /jongga-v2/* 엔드포인트.
# 기존 핸들러를 재사용하므로 로직 중복 없음.
# ─────────────────────────────────────────

@kr_bp.route("/jongga-v2/latest")
def jongga_v2_latest():
    """
    GET /api/kr/jongga-v2/latest
    최신 종가베팅 V2 분석 결과 (ai-analysis와 동일)
    """
    return ai_analysis()


@kr_bp.route("/jongga-v2/dates")
def jongga_v2_dates():
    """
    GET /api/kr/jongga-v2/dates
    분석 결과 히스토리 날짜 목록 (ai-history-dates와 동일)
    """
    return ai_history_dates()


@kr_bp.route("/jongga-v2/history/<hist_date>")
def jongga_v2_history(hist_date: str):
    """
    GET /api/kr/jongga-v2/history/<date>
    특정 날짜 분석 결과 (ai-history/<date>와 동일)
    """
    return ai_history(hist_date)


@kr_bp.route("/jongga-v2/run", methods=["POST"])
def jongga_v2_run():
    """
    POST /api/kr/jongga-v2/run
    종가베팅 V2 엔진 실행 (vcp-scan과 동일)
    Body: { "capital": 50000000 }
    """
    return vcp_scan()
