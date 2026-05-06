"""KIS 주문 (현금) — 매수/매도.

엔드포인트: POST /uapi/domestic-stock/v1/trading/order-cash
"""
from __future__ import annotations

import logging
from typing import Optional

import aiohttp

from broker.kis.config import KISConfig
from broker.kis.models import OrderRequest, OrderResponse, OrderSide
from broker.kis.rest import request

logger = logging.getLogger(__name__)

ORDER_PATH = "/uapi/domestic-stock/v1/trading/order-cash"


def _build_body(cfg: KISConfig, req: OrderRequest) -> dict:
    return {
        "CANO": cfg.cano,
        "ACNT_PRDT_CD": cfg.acnt_prdt_cd,
        "PDNO": req.ticker,
        "ORD_DVSN": req.order_type.value,
        "ORD_QTY": str(req.quantity),
        "ORD_UNPR": str(req.price),
    }


def _parse_response(data: dict) -> OrderResponse:
    rt_cd = str(data.get("rt_cd", ""))
    output = data.get("output", {}) or {}
    return OrderResponse(
        ok=(rt_cd == "0"),
        rt_cd=rt_cd,
        msg_cd=str(data.get("msg_cd", "")),
        msg=str(data.get("msg1", "")),
        order_no=f"{output.get('KRX_FWDG_ORD_ORGNO','')}-{output.get('ODNO','')}",
        odno=str(output.get("ODNO", "")),
        ord_tmd=str(output.get("ORD_TMD", "")),
        raw=data,
    )


async def place_order(
    cfg: KISConfig,
    req: OrderRequest,
    *,
    session: Optional[aiohttp.ClientSession] = None,
) -> OrderResponse:
    """매수/매도 주문 단건 전송."""
    tr_key = "order_buy" if req.side == OrderSide.BUY else "order_sell"
    tr_id = cfg.tr_id(tr_key)
    body = _build_body(cfg, req)
    data = await request(
        cfg, "POST", ORDER_PATH, tr_id=tr_id, body=body, session=session,
    )
    res = _parse_response(data)
    if res.ok:
        logger.info(
            f"[KIS] {req.side.value.upper()} {req.ticker} qty={req.quantity} "
            f"price={req.price} → ODNO={res.odno}"
        )
    else:
        logger.warning(
            f"[KIS] 주문 실패 {req.side.value} {req.ticker}: {res.msg_cd} {res.msg}"
        )
    return res


async def place_buy(
    cfg: KISConfig, ticker: str, quantity: int, price: int = 0,
    *, market: bool = False, session: Optional[aiohttp.ClientSession] = None,
) -> OrderResponse:
    """매수 단축 헬퍼. market=True 면 시장가."""
    from broker.kis.models import OrderType
    return await place_order(cfg, OrderRequest(
        ticker=ticker, side=OrderSide.BUY, quantity=quantity,
        order_type=OrderType.MARKET if market else OrderType.LIMIT,
        price=0 if market else price,
    ), session=session)


async def place_sell(
    cfg: KISConfig, ticker: str, quantity: int, price: int = 0,
    *, market: bool = False, session: Optional[aiohttp.ClientSession] = None,
) -> OrderResponse:
    """매도 단축 헬퍼."""
    from broker.kis.models import OrderType
    return await place_order(cfg, OrderRequest(
        ticker=ticker, side=OrderSide.SELL, quantity=quantity,
        order_type=OrderType.MARKET if market else OrderType.LIMIT,
        price=0 if market else price,
    ), session=session)
