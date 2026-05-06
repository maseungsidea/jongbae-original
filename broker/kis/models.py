"""KIS 주문/잔고 데이터 모델."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    """KIS ORD_DVSN: 00=지정가, 01=시장가."""
    LIMIT = "00"
    MARKET = "01"


@dataclass(frozen=True)
class OrderRequest:
    ticker: str           # 6자리 종목코드
    side: OrderSide
    quantity: int
    order_type: OrderType = OrderType.LIMIT
    price: int = 0        # 시장가일 때는 0

    def __post_init__(self):
        if self.quantity <= 0:
            raise ValueError(f"quantity must be > 0, got {self.quantity}")
        if self.order_type == OrderType.LIMIT and self.price <= 0:
            raise ValueError("LIMIT order requires price > 0")
        if self.order_type == OrderType.MARKET and self.price != 0:
            raise ValueError("MARKET order requires price == 0")
        if not (self.ticker.isdigit() and len(self.ticker) == 6):
            raise ValueError(f"ticker must be 6 digits, got {self.ticker!r}")


@dataclass(frozen=True)
class OrderResponse:
    """KIS 주문 응답 (현금주문 기준)."""
    ok: bool
    rt_cd: str            # KIS 응답코드 (0=정상)
    msg_cd: str           # 메시지 코드
    msg: str              # 메시지 본문
    order_no: str = ""    # KRX_FWDG_ORD_ORGNO + ODNO 조합 (체결조회 키)
    odno: str = ""        # 주문번호
    ord_tmd: str = ""     # 주문시각 HHMMSS
    raw: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Position:
    ticker: str
    name: str
    quantity: int         # 보유수량
    avg_price: float      # 평균매입가
    current_price: float  # 현재가
    eval_amount: int      # 평가금액
    pnl: int              # 평가손익
    pnl_pct: float        # 수익률 %


@dataclass(frozen=True)
class AccountSnapshot:
    """잔고 조회 한 번의 스냅샷."""
    cash: int                       # 예수금 (D+2 기준)
    total_eval: int                 # 총평가금액
    total_pnl: int                  # 총평가손익
    total_pnl_pct: float            # 총수익률 %
    positions: tuple[Position, ...] = ()
    fetched_at: datetime = field(default_factory=datetime.now)
