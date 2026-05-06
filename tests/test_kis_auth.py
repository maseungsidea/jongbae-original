"""KIS auth 모듈: 캐시 재사용, 만료 갱신, 환경 분리 테스트."""
from __future__ import annotations

import asyncio
import json
import time
from unittest.mock import AsyncMock, patch

import pytest

from broker.kis import auth
from broker.kis.auth import Token, _load_cache, _save_cache, get_token
from broker.kis.config import KISConfig, KISEnv


def _cfg(env: KISEnv = KISEnv.MOCK) -> KISConfig:
    return KISConfig(
        env=env, app_key="k", app_secret="s",
        cano="12345678", acnt_prdt_cd="01",
    )


@pytest.fixture
def tmp_cache(monkeypatch, tmp_path):
    cache = tmp_path / "kis_token.json"
    monkeypatch.setattr(auth, "CACHE_PATH", cache)
    return cache


class TestTokenIsValid:
    def test_future_expiry(self):
        assert Token("x", time.time() + 3600).is_valid

    def test_past_expiry(self):
        assert not Token("x", time.time() - 1).is_valid

    def test_inside_buffer_invalid(self):
        # 만료 30초 전(buffer=60s) → invalid 로 판정해 갱신 유도
        assert not Token("x", time.time() + 30).is_valid


class TestCacheRoundtrip:
    def test_save_and_load(self, tmp_cache):
        tok = Token("abc", time.time() + 3600)
        _save_cache("mock", tok)
        loaded = _load_cache("mock")
        assert loaded is not None
        assert loaded.access_token == "abc"

    def test_env_mismatch_returns_none(self, tmp_cache):
        _save_cache("mock", Token("abc", time.time() + 3600))
        assert _load_cache("prod") is None

    def test_expired_returns_none(self, tmp_cache):
        _save_cache("mock", Token("abc", time.time() - 1))
        assert _load_cache("mock") is None

    def test_corrupt_file_returns_none(self, tmp_cache):
        tmp_cache.write_text("not json")
        assert _load_cache("mock") is None

    def test_missing_file_returns_none(self, tmp_cache):
        assert _load_cache("mock") is None


class TestGetToken:
    def test_uses_cache_when_valid(self, tmp_cache):
        _save_cache("mock", Token("cached", time.time() + 3600))
        with patch.object(auth, "issue_token", new=AsyncMock()) as m:
            tok = asyncio.run(get_token(_cfg()))
        assert tok.access_token == "cached"
        m.assert_not_called()

    def test_force_refresh_skips_cache(self, tmp_cache):
        _save_cache("mock", Token("cached", time.time() + 3600))
        new_tok = Token("fresh", time.time() + 7200)
        with patch.object(auth, "issue_token", new=AsyncMock(return_value=new_tok)) as m:
            tok = asyncio.run(get_token(_cfg(), force_refresh=True))
        assert tok.access_token == "fresh"
        m.assert_called_once()

    def test_issues_when_no_cache(self, tmp_cache):
        new_tok = Token("issued", time.time() + 86400)
        with patch.object(auth, "issue_token", new=AsyncMock(return_value=new_tok)) as m:
            tok = asyncio.run(get_token(_cfg()))
        assert tok.access_token == "issued"
        m.assert_called_once()
        # 캐시 저장 확인
        cached = _load_cache("mock")
        assert cached is not None and cached.access_token == "issued"
