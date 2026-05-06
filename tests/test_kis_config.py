"""KISConfig 환경변수 파싱 + URL/TR_ID 분기 테스트."""
from __future__ import annotations

import pytest

from broker.kis.config import KISConfig, KISEnv, _parse_account


class TestParseAccount:
    def test_valid_format(self):
        assert _parse_account("12345678-01") == ("12345678", "01")

    def test_missing_dash(self):
        with pytest.raises(ValueError, match="CANO-PRDT"):
            _parse_account("1234567801")

    def test_cano_wrong_length(self):
        with pytest.raises(ValueError, match="8 digits"):
            _parse_account("1234-01")

    def test_prdt_wrong_length(self):
        with pytest.raises(ValueError, match="2 digits"):
            _parse_account("12345678-1")

    def test_non_digit(self):
        with pytest.raises(ValueError, match="8 digits"):
            _parse_account("ABCDEFGH-01")


class TestFromEnv:
    def _set_env(self, monkeypatch, **overrides):
        defaults = {
            "KIS_ENV": "mock",
            "KIS_APP_KEY": "appkey123",
            "KIS_APP_SECRET": "secret456",
            "KIS_ACCOUNT_NO": "12345678-01",
        }
        defaults.update(overrides)
        for k, v in defaults.items():
            monkeypatch.setenv(k, v)

    def test_mock_default(self, monkeypatch):
        self._set_env(monkeypatch)
        cfg = KISConfig.from_env()
        assert cfg.env == KISEnv.MOCK
        assert cfg.is_mock
        assert "openapivts" in cfg.base_url
        assert cfg.cano == "12345678"
        assert cfg.acnt_prdt_cd == "01"
        assert cfg.custtype == "P"

    def test_prod_env(self, monkeypatch):
        self._set_env(monkeypatch, KIS_ENV="prod")
        cfg = KISConfig.from_env()
        assert cfg.env == KISEnv.PROD
        assert not cfg.is_mock
        assert "openapi.koreainvestment" in cfg.base_url

    def test_invalid_env(self, monkeypatch):
        self._set_env(monkeypatch, KIS_ENV="staging")
        with pytest.raises(ValueError, match="must be 'mock' or 'prod'"):
            KISConfig.from_env()

    def test_missing_key(self, monkeypatch):
        self._set_env(monkeypatch, KIS_APP_KEY="")
        with pytest.raises(ValueError, match="KIS_APP_KEY"):
            KISConfig.from_env()

    def test_tr_id_mock_vs_prod(self, monkeypatch):
        self._set_env(monkeypatch, KIS_ENV="mock")
        mock_cfg = KISConfig.from_env()
        self._set_env(monkeypatch, KIS_ENV="prod")
        prod_cfg = KISConfig.from_env()
        assert mock_cfg.tr_id("order_buy").startswith("V")
        assert prod_cfg.tr_id("order_buy").startswith("T")
        assert mock_cfg.tr_id("balance") != prod_cfg.tr_id("balance")
