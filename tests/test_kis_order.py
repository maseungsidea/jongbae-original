"""KIS order 모듈: 요청 본문 형식 + 응답 파싱 + TR_ID 분기 테스트."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from broker.kis.config import KISConfig, KISEnv
from broker.kis.models import OrderRequest, OrderSide, OrderType
from broker.kis.order import _build_body, _parse_response, place_buy, place_sell


def _cfg(env: KISEnv = KISEnv.MOCK) -> KISConfig:
    return KISConfig(
        env=env, app_key="k", app_secret="s",
        cano="12345678", acnt_prdt_cd="01",
    )


class TestOrderRequestValidation:
    def test_valid_limit(self):
        req = OrderRequest("005930", OrderSide.BUY, 10, OrderType.LIMIT, 70000)
        assert req.quantity == 10

    def test_market_requires_zero_price(self):
        with pytest.raises(ValueError, match="MARKET order requires price == 0"):
            OrderRequest("005930", OrderSide.BUY, 10, OrderType.MARKET, 70000)

    def test_limit_requires_positive_price(self):
        with pytest.raises(ValueError, match="price > 0"):
            OrderRequest("005930", OrderSide.BUY, 10, OrderType.LIMIT, 0)

    def test_zero_quantity(self):
        with pytest.raises(ValueError, match="quantity must be > 0"):
            OrderRequest("005930", OrderSide.BUY, 0, OrderType.LIMIT, 70000)

    def test_invalid_ticker(self):
        with pytest.raises(ValueError, match="6 digits"):
            OrderRequest("ABC", OrderSide.BUY, 10, OrderType.LIMIT, 70000)


class TestBuildBody:
    def test_limit_buy(self):
        cfg = _cfg()
        req = OrderRequest("005930", OrderSide.BUY, 10, OrderType.LIMIT, 70000)
        body = _build_body(cfg, req)
        assert body == {
            "CANO": "12345678",
            "ACNT_PRDT_CD": "01",
            "PDNO": "005930",
            "ORD_DVSN": "00",
            "ORD_QTY": "10",
            "ORD_UNPR": "70000",
        }

    def test_market_sell(self):
        cfg = _cfg()
        req = OrderRequest("000660", OrderSide.SELL, 5, OrderType.MARKET, 0)
        body = _build_body(cfg, req)
        assert body["ORD_DVSN"] == "01"
        assert body["ORD_UNPR"] == "0"


class TestParseResponse:
    def test_success(self):
        data = {
            "rt_cd": "0", "msg_cd": "APBK0013", "msg1": "주문이 완료되었습니다",
            "output": {
                "KRX_FWDG_ORD_ORGNO": "00950",
                "ODNO": "0000123456",
                "ORD_TMD": "133045",
            },
        }
        res = _parse_response(data)
        assert res.ok
        assert res.odno == "0000123456"
        assert res.order_no == "00950-0000123456"

    def test_failure(self):
        data = {"rt_cd": "1", "msg_cd": "EGW00121", "msg1": "주문가능금액 부족"}
        res = _parse_response(data)
        assert not res.ok
        assert res.msg_cd == "EGW00121"
        assert "부족" in res.msg


class TestPlaceOrderRouting:
    """place_buy/sell 이 올바른 TR_ID 를 사용하는지 확인."""

    def _mock_request(self, expected_tr_id: str):
        """request() 호출 시 tr_id 검증 후 성공 응답 반환."""
        async def fake(cfg, method, path, *, tr_id, body=None, params=None, session=None):
            assert tr_id == expected_tr_id, f"expected {expected_tr_id}, got {tr_id}"
            assert method == "POST"
            assert "order-cash" in path
            return {"rt_cd": "0", "msg_cd": "OK", "msg1": "ok",
                    "output": {"KRX_FWDG_ORD_ORGNO": "1", "ODNO": "2", "ORD_TMD": "100000"}}
        return fake

    def test_mock_buy_uses_vttc(self):
        cfg = _cfg(KISEnv.MOCK)
        with patch("broker.kis.order.request", new=self._mock_request("VTTC0802U")):
            res = asyncio.run(place_buy(cfg, "005930", 10, 70000))
        assert res.ok

    def test_prod_buy_uses_tttc(self):
        cfg = _cfg(KISEnv.PROD)
        with patch("broker.kis.order.request", new=self._mock_request("TTTC0802U")):
            res = asyncio.run(place_buy(cfg, "005930", 10, 70000))
        assert res.ok

    def test_mock_sell_uses_vttc_sell(self):
        cfg = _cfg(KISEnv.MOCK)
        with patch("broker.kis.order.request", new=self._mock_request("VTTC0801U")):
            res = asyncio.run(place_sell(cfg, "005930", 10, 70000))
        assert res.ok

    def test_market_buy_zero_price(self):
        cfg = _cfg(KISEnv.MOCK)
        captured = {}

        async def fake(cfg, method, path, *, tr_id, body=None, params=None, session=None):
            captured["body"] = body
            return {"rt_cd": "0", "msg_cd": "OK", "msg1": "ok", "output": {}}

        with patch("broker.kis.order.request", new=fake):
            asyncio.run(place_buy(cfg, "005930", 10, market=True))
        assert captured["body"]["ORD_DVSN"] == "01"
        assert captured["body"]["ORD_UNPR"] == "0"
