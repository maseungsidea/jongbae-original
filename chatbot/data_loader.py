"""
챗봇 데이터 로더 (chatbot/data_loader.py)

챗봇이 답변할 때 참조할 시장 데이터를 로드하여
간결한 텍스트 컨텍스트로 변환합니다.

LLM에게 불필요한 원시 데이터 대신 핵심 요약만 전달하여
토큰 비용을 최소화합니다.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"


def get_market_context() -> str:
    """
    최신 마켓 상태와 시그널 요약 텍스트를 반환합니다.
    챗봇 시스템 프롬프트의 컨텍스트로 주입됩니다.

    Returns:
        시장 상황 요약 문자열 (없으면 빈 문자열)
    """
    parts = []

    # 1. Market Gate 상태
    try:
        from market_gate import run_kr_market_gate
        gate = run_kr_market_gate()
        parts.append(
            f"[마켓 게이트] {gate.gate} (점수: {gate.score}/100)\n"
            f"  근거: {', '.join(gate.reasons[:3])}"
        )
    except Exception as e:
        logger.debug(f"[data_loader] market gate 로드 실패: {e}")

    # 2. 오늘의 시그널 요약
    try:
        import signal_tracker
        df = signal_tracker.get_today_signals()
        if not df.empty:
            top = df.sort_values("score", ascending=False).head(5)
            lines = []
            for _, row in top.iterrows():
                lines.append(f"  - {row['name']}({row['ticker']}) {row['grade']}등급 {row['score']}점")
            parts.append("[오늘 시그널]\n" + "\n".join(lines))
        else:
            parts.append("[오늘 시그널] 없음")
    except Exception as e:
        logger.debug(f"[data_loader] 시그널 로드 실패: {e}")

    # 3. 성과 요약
    try:
        import signal_tracker
        df = signal_tracker._load()
        if not df.empty:
            closed = df[df["status"] == "exited"]
            total = len(closed)
            if total > 0:
                wins = len(closed[closed["return_pct"] > 0])
                avg = closed["return_pct"].mean()
                parts.append(f"[성과] 총 {total}건, 승률 {wins/total*100:.1f}%, 평균수익 {avg:+.1f}%")
    except Exception as e:
        logger.debug(f"[data_loader] 성과 로드 실패: {e}")

    return "\n\n".join(parts) if parts else ""


def get_stock_context(ticker: str) -> str:
    """
    특정 종목의 최신 데이터를 텍스트로 반환합니다.

    Args:
        ticker: 6자리 종목코드

    Returns:
        종목 데이터 요약 문자열
    """
    try:
        import pandas as pd
        prices_path = DATA_DIR / "daily_prices.csv"
        if not prices_path.exists():
            return ""

        df = pd.read_csv(prices_path, dtype={"ticker": str})
        df = df[df["ticker"] == ticker.zfill(6)].sort_values("date")

        if df.empty:
            return f"{ticker}: 데이터 없음"

        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) >= 2 else latest

        change_pct = (latest["close"] - prev["close"]) / prev["close"] * 100
        return (
            f"[{ticker}] 최근 종가: {int(latest['close']):,}원 ({change_pct:+.1f}%) "
            f"| 날짜: {latest['date']}"
        )
    except Exception as e:
        logger.debug(f"[data_loader] 종목({ticker}) 컨텍스트 로드 실패: {e}")
        return ""
