"""KIS REST 호출 저수준 래퍼.

토큰 자동 주입 + tr_id/custtype 헤더 + 표준 에러 처리.
주문/잔고 모듈은 이 모듈의 request() 만 사용한다.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import aiohttp

from broker.kis.auth import get_token
from broker.kis.config import KISConfig

logger = logging.getLogger(__name__)


async def request(
    cfg: KISConfig,
    method: str,
    path: str,
    *,
    tr_id: str,
    body: Optional[dict] = None,
    params: Optional[dict] = None,
    session: Optional[aiohttp.ClientSession] = None,
    timeout_sec: int = 10,
) -> dict[str, Any]:
    """KIS REST 호출. 응답 dict 반환 (rt_cd 검증은 호출자 책임).

    Args:
        method   : "GET" | "POST"
        path     : "/uapi/..."로 시작하는 경로
        tr_id    : KIS TR_ID (cfg.tr_id() 로 환경별 분기 후 전달)
        body     : POST body (dict → JSON)
        params   : GET query string
        session  : 재사용할 ClientSession (None 이면 매 호출 신규)
    """
    token = await get_token(cfg, session=session)
    url = f"{cfg.base_url}{path}"
    headers = {
        "content-type": "application/json; charset=utf-8",
        "authorization": f"Bearer {token.access_token}",
        "appkey": cfg.app_key,
        "appsecret": cfg.app_secret,
        "tr_id": tr_id,
        "custtype": cfg.custtype,
    }
    own = session is None
    if own:
        session = aiohttp.ClientSession()
    try:
        async with session.request(
            method, url, headers=headers,
            json=body if body is not None else None,
            params=params,
            timeout=aiohttp.ClientTimeout(total=timeout_sec),
        ) as resp:
            data = await resp.json(content_type=None)
            if resp.status != 200:
                logger.warning(f"[KIS] {method} {path} → HTTP {resp.status}: {data}")
            return data
    finally:
        if own:
            await session.close()
