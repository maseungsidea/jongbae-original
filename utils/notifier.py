"""Telegram 알림 모듈.

운영 시 시그널 채택 / 주문 체결 / 에러 발생 알림을 보낸다.

환경변수:
    TELEGRAM_TOKEN     : Bot API 토큰 (BotFather 발급)
    TELEGRAM_CHAT_ID   : 수신 chat_id
    JONGGA_NOTIFY      : "0" 이면 강제 비활성 (백테/테스트용). default=1.

설계 노트:
- 동기(urllib) 호출 — Telegram API 는 단발성이라 async 가 불필요.
  scorer/order 모듈은 호출 후 결과를 기다리지 않으므로 latency 무관.
- 자격증명이 없거나 비활성 시 graceful no-op (False 반환). 절대 예외를 던지지 않는다.
- HTML parse_mode 사용 — 메시지에서 사용자 입력은 _escape_html() 로 통과.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.parse
import urllib.request
from typing import Optional

logger = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org"
TIMEOUT_SEC = 5


def _enabled() -> bool:
    """알림 허용 여부. JONGGA_NOTIFY=0 이면 강제 비활성."""
    return os.getenv("JONGGA_NOTIFY", "1") != "0"


def _credentials() -> Optional[tuple[str, str]]:
    token = os.getenv("TELEGRAM_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if token and chat_id:
        return token, chat_id
    return None


def _escape_html(s: str) -> str:
    return (
        s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


def send_message(text: str, *, parse_mode: str = "HTML") -> bool:
    """Telegram 메시지 전송. 실패/비활성 시 False, 성공 시 True."""
    if not _enabled():
        return False
    creds = _credentials()
    if creds is None:
        logger.debug("[notifier] TELEGRAM_TOKEN/CHAT_ID 미설정 → skip")
        return False
    token, chat_id = creds
    url = f"{API_BASE}/bot{token}/sendMessage"
    payload = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": "true",
    }).encode()
    try:
        req = urllib.request.Request(url, data=payload, method="POST")
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
            if resp.status != 200:
                logger.warning(f"[notifier] HTTP {resp.status}")
                return False
            body = json.loads(resp.read().decode())
            return bool(body.get("ok"))
    except Exception as e:
        # 네트워크/토큰 오류로 운영 흐름이 죽지 않도록 swallow
        logger.warning(f"[notifier] 전송 실패: {type(e).__name__}: {e}")
        return False


def notify_signal(
    *, ticker: str, name: str, grade: str, score: int,
    entry_price: float, stop_price: float = 0, target_price: float = 0,
    market: str = "", trading_value: int = 0,
) -> bool:
    """시그널 채택 알림 (Grade B+ 시점).

    stop_price/target_price 가 0 이면 해당 줄 생략 — scorer 단계에서는
    PositionSizer 미실행 상태라 두 값을 모르기 때문.
    """
    e = _escape_html
    lines = [
        f"📈 <b>[{e(grade)}] {e(name)} ({e(ticker)})</b>",
        f"점수 {score}점 · {e(market)}" if market else f"점수 {score}점",
    ]
    if entry_price:
        if stop_price and target_price:
            lines.append(
                f"진입 {entry_price:,.0f}  손절 {stop_price:,.0f}  목표 {target_price:,.0f}"
            )
        else:
            lines.append(f"현재가 {entry_price:,.0f}")
    if trading_value:
        lines.append(f"거래대금 {trading_value/1e8:,.0f}억")
    return send_message("\n".join(lines))


def notify_order(
    *, side: str, ticker: str, quantity: int, price: int,
    ok: bool, msg: str = "", odno: str = "",
) -> bool:
    """KIS 주문 체결 결과 알림."""
    e = _escape_html
    icon = "🟢" if ok else "🔴"
    side_kr = "매수" if side.lower() == "buy" else "매도"
    head = f"{icon} <b>{side_kr} {e(ticker)}</b> {quantity}주 @ {price:,}"
    if ok:
        body = f"주문번호 {e(odno)}" if odno else "체결 완료"
    else:
        body = f"실패: {e(msg)}"
    return send_message(f"{head}\n{body}")


def notify_error(context: str, err: BaseException) -> bool:
    """운영 중 예외 발생 알림."""
    e = _escape_html
    text = f"⚠️ <b>{e(context)}</b>\n{e(type(err).__name__)}: {e(str(err))[:300]}"
    return send_message(text)
