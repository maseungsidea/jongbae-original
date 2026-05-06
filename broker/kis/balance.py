"""KIS 잔고/매수가능금액 조회.

엔드포인트:
  - GET /uapi/domestic-stock/v1/trading/inquire-balance       (보유종목 + 평가)
  - GET /uapi/domestic-stock/v1/trading/inquire-psbl-order    (매수가능금액)
"""
from __future__ import annotations

import logging
from typing import Optional

import aiohttp

from broker.kis.config import KISConfig
from broker.kis.models import AccountSnapshot, Position
from broker.kis.rest import request

logger = logging.getLogger(__name__)

BALANCE_PATH = "/uapi/domestic-stock/v1/trading/inquire-balance"
PSBL_ORDER_PATH = "/uapi/domestic-stock/v1/trading/inquire-psbl-order"


def _to_int(v) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def _to_float(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _parse_position(row: dict) -> Position:
    return Position(
        ticker=str(row.get("pdno", "")).zfill(6),
        name=str(row.get("prdt_name", "")),
        quantity=_to_int(row.get("hldg_qty")),
        avg_price=_to_float(row.get("pchs_avg_pric")),
        current_price=_to_float(row.get("prpr")),
        eval_amount=_to_int(row.get("evlu_amt")),
        pnl=_to_int(row.get("evlu_pfls_amt")),
        pnl_pct=_to_float(row.get("evlu_pfls_rt")),
    )


async def get_balance(
    cfg: KISConfig, *, session: Optional[aiohttp.ClientSession] = None,
) -> AccountSnapshot:
    """보유종목 + 총평가 스냅샷."""
    tr_id = cfg.tr_id("balance")
    params = {
        "CANO": cfg.cano,
        "ACNT_PRDT_CD": cfg.acnt_prdt_cd,
        "AFHR_FLPR_YN": "N",   # 시간외단일가포함여부
        "OFL_YN": "",
        "INQR_DVSN": "02",     # 02=종목별
        "UNPR_DVSN": "01",     # 01=원평균단가
        "FUND_STTL_ICLD_YN": "N",
        "FNCG_AMT_AUTO_RDPT_YN": "N",
        "PRCS_DVSN": "00",
        "CTX_AREA_FK100": "",
        "CTX_AREA_NK100": "",
    }
    data = await request(
        cfg, "GET", BALANCE_PATH, tr_id=tr_id, params=params, session=session,
    )
    if str(data.get("rt_cd", "")) != "0":
        logger.warning(f"[KIS] 잔고조회 실패: {data.get('msg_cd')} {data.get('msg1')}")
    holdings = data.get("output1", []) or []
    summary_list = data.get("output2", []) or [{}]
    summary = summary_list[0] if summary_list else {}

    positions = tuple(
        _parse_position(r) for r in holdings if _to_int(r.get("hldg_qty")) > 0
    )
    return AccountSnapshot(
        cash=_to_int(summary.get("dnca_tot_amt")),         # 예수금총금액
        total_eval=_to_int(summary.get("tot_evlu_amt")),
        total_pnl=_to_int(summary.get("evlu_pfls_smtl_amt")),
        total_pnl_pct=_to_float(summary.get("asst_icdc_erng_rt")),
        positions=positions,
    )


async def get_orderable_amount(
    cfg: KISConfig, ticker: str, price: int,
    *, session: Optional[aiohttp.ClientSession] = None,
) -> int:
    """특정 종목 매수가능금액 (원). 포지션사이저 검증용."""
    tr_id = cfg.tr_id("psbl_order")
    params = {
        "CANO": cfg.cano,
        "ACNT_PRDT_CD": cfg.acnt_prdt_cd,
        "PDNO": ticker,
        "ORD_UNPR": str(price),
        "ORD_DVSN": "00",
        "CMA_EVLU_AMT_ICLD_YN": "N",
        "OVRS_ICLD_YN": "N",
    }
    data = await request(
        cfg, "GET", PSBL_ORDER_PATH, tr_id=tr_id, params=params, session=session,
    )
    output = data.get("output", {}) or {}
    return _to_int(output.get("ord_psbl_cash"))
