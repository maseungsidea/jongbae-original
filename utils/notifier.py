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


def notify_today_recommendations(
    path: str = "data/today_recommendations.json",
    candidates_path: str = "data/jongga_v2_candidates.json",
    *, max_items: int = 20, max_near_miss: int = 5,
) -> bool:
    """일일 추천종목 + 아깝게 탈락한 종목을 단일 텔레그램 메시지로 발송.

    Args:
        path: 통과 종목 슬림 파일 (today_recommendations.json)
        candidates_path: 후보 전체 결과 파일 (jongga_v2_candidates.json)
        max_items: 추천(통과) 종목 표시 상한
        max_near_miss: 아깝게 탈락(점수 상위 미통과) 표시 상한

    파일이 둘 다 없으면 False, 한쪽만 있으면 가능한 섹션만 보낸다.
    """
    e = _escape_html
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except FileNotFoundError:
        # 추천 파일 없음 = 스캔 미실행 → 발송 스킵 (near miss 도 의미 없음)
        logger.info(f"[notifier] {path} 없음 → skip")
        return False
    except Exception as ex:
        logger.warning(f"[notifier] {path} 읽기 실패: {ex}")
        return False

    items = payload.get("items", []) or []
    date_str = payload.get("date") or ""

    header = f"📈 <b>오늘 추천종목</b>"
    if date_str:
        header += f" ({e(date_str)})"

    lines = [header]
    if items:
        for i, it in enumerate(items[:max_items], start=1):
            grade = e(str(it.get("grade", "")))
            name = e(str(it.get("name", "")))
            ticker = e(str(it.get("ticker", "")))
            score = it.get("score", 0)
            price = it.get("price", 0)
            tv = it.get("trading_value", 0) or 0
            line = (
                f"{i}. <b>{name}</b> ({ticker}) [Grade {grade}] "
                f"{score}점 · {price:,}원"
            )
            if tv:
                line += f" · 거래대금 {tv/1e8:,.0f}억"
            lines.append(line)
        if len(items) > max_items:
            lines.append(f"… 외 {len(items) - max_items}개")
    else:
        lines.append("조건에 맞는 종목 없음")

    # 아깝게 탈락 (score 내림차순 상위 max_near_miss 개)
    near_miss_lines = _format_near_miss(candidates_path, max_near_miss, e)
    if near_miss_lines:
        lines.append("")
        lines.extend(near_miss_lines)

    return send_message("\n".join(lines))


def _format_near_miss(candidates_path: str, max_n: int, e) -> list:
    """후보 JSON 에서 점수 상위 탈락 종목 라인 빌드. 파일/데이터 없으면 []."""
    try:
        with open(candidates_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except FileNotFoundError:
        return []
    except Exception as ex:
        logger.warning(f"[notifier] {candidates_path} 읽기 실패: {ex}")
        return []

    rejected = payload.get("rejected", []) or []
    if not rejected:
        return []

    # 점수 DESC, 동점이면 거래대금 DESC
    rejected_sorted = sorted(
        rejected,
        key=lambda c: (-int(c.get("score", 0) or 0), -int(c.get("trading_value", 0) or 0)),
    )[:max_n]

    out = ["🥲 <b>아깝게 탈락한 종목</b>"]
    for i, c in enumerate(rejected_sorted, start=1):
        name = e(str(c.get("name", "")))
        ticker = e(str(c.get("ticker", "")))
        score = c.get("score", 0)
        change = c.get("change_pct", 0) or 0
        reasons = c.get("reasons", []) or []
        reason_short = " / ".join(e(str(r)) for r in reasons[:2]) or "-"
        out.append(
            f"{i}. <b>{name}</b> ({ticker}) {score}점 · {change:+.2f}%\n   {reason_short}"
        )
    return out


def notify_error(context: str, err: BaseException) -> bool:
    """운영 중 예외 발생 알림."""
    e = _escape_html
    text = f"⚠️ <b>{e(context)}</b>\n{e(type(err).__name__)}: {e(str(err))[:300]}"
    return send_message(text)
