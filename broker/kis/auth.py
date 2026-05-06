"""KIS OAuth 토큰 발급 + 24h 파일 캐시.

KIS access_token TTL = 24h. 발급 회수 제한이 있으므로 파일에 캐시하고
재사용한다 (data/kis_token.json).
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import aiohttp

from broker.kis.config import KISConfig

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent
CACHE_PATH = ROOT / "data" / "kis_token.json"

# 만료 60초 전부터는 갱신 (clock skew 안전 여유)
EXPIRY_BUFFER_SEC = 60


@dataclass(frozen=True)
class Token:
    access_token: str
    expires_at: float       # epoch seconds

    @property
    def is_valid(self) -> bool:
        return time.time() < (self.expires_at - EXPIRY_BUFFER_SEC)


def _load_cache(env: str) -> Optional[Token]:
    """파일 캐시에서 토큰 로드. 환경(mock/prod) 일치 + 만료 전이면 반환."""
    if not CACHE_PATH.exists():
        return None
    try:
        blob = json.loads(CACHE_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    if blob.get("env") != env:
        return None
    tok = Token(access_token=blob["access_token"], expires_at=blob["expires_at"])
    return tok if tok.is_valid else None


def _save_cache(env: str, token: Token) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps({
        "env": env,
        "access_token": token.access_token,
        "expires_at": token.expires_at,
    }))


async def issue_token(
    cfg: KISConfig,
    session: Optional[aiohttp.ClientSession] = None,
) -> Token:
    """OAuth 토큰을 발급받아 반환. (캐시 미사용 — 강제 재발급)"""
    url = f"{cfg.base_url}/oauth2/tokenP"
    body = {
        "grant_type": "client_credentials",
        "appkey": cfg.app_key,
        "appsecret": cfg.app_secret,
    }
    own_session = session is None
    if own_session:
        session = aiohttp.ClientSession()
    try:
        async with session.post(url, json=body, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            data = await resp.json()
            if resp.status != 200 or "access_token" not in data:
                raise RuntimeError(f"KIS token issue failed: {resp.status} {data}")
    finally:
        if own_session:
            await session.close()
    # KIS 응답 expires_in(초). 안전하게 클라이언트 측에서 epoch 로 환산.
    expires_in = int(data.get("expires_in", 86400))
    token = Token(
        access_token=data["access_token"],
        expires_at=time.time() + expires_in,
    )
    return token


async def get_token(
    cfg: KISConfig,
    session: Optional[aiohttp.ClientSession] = None,
    force_refresh: bool = False,
) -> Token:
    """캐시 우선 → 만료/없음 시 발급."""
    if not force_refresh:
        cached = _load_cache(cfg.env.value)
        if cached is not None:
            return cached
    token = await issue_token(cfg, session=session)
    _save_cache(cfg.env.value, token)
    logger.info(f"[KIS] 토큰 발급 ({cfg.env.value}, exp={int(token.expires_at - time.time())}s)")
    return token
