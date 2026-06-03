"""
hub_client.py — Trading Hub 클라이언트
각 투자앱에 이 파일 1개를 복사하고 requirements.txt에 httpx 추가.

환경변수 필요:
  HUB_URL    = https://trading-hub.up.railway.app
  HUB_SECRET = <공유 시크릿>

사용 예:
  from hub_client import HubClient
  hub = HubClient("my-app-id")
  hub.push_signal("005930", score=87.4)
  hub.push_buy("005930", price=72000, qty=10)
  hub.push_sell("005930", price=74800, pnl_pct=3.9)
  hub.push_heartbeat()                    # APScheduler 5분마다
  hub.push_snapshot(date="2026-06-02", signal_count=2, ...)  # 15:35 KST
"""
import os
from typing import Optional
import httpx

HUB_URL = os.getenv("HUB_URL", "")
HUB_SECRET = os.getenv("HUB_SECRET", "")


class HubClient:
    def __init__(self, app_id: str) -> None:
        self.app_id = app_id
        self.url = HUB_URL
        self.secret = HUB_SECRET

    def _send(self, event_type: str, ticker: Optional[str] = None,
              data: Optional[dict] = None, timeout: float = 3.0) -> None:
        if not self.url:
            return
        try:
            httpx.post(
                f"{self.url}/api/events/{self.app_id}",
                json={"type": event_type, "ticker": ticker, "data": data or {}},
                headers={"X-Hub-Secret": self.secret},
                timeout=timeout,
            )
        except Exception:
            pass

    def push_signal(self, ticker: str, score: float, **kwargs) -> None:
        self._send("signal", ticker=ticker, data={"score": score, **kwargs})

    def push_buy(self, ticker: str, price: int, qty: int, **kwargs) -> None:
        self._send("buy", ticker=ticker, data={"price": price, "qty": qty, **kwargs})

    def push_sell(self, ticker: str, price: int, pnl_pct: float, **kwargs) -> None:
        self._send("sell", ticker=ticker, data={"price": price, "pnl_pct": pnl_pct, **kwargs})

    def push_error(self, message: str, **kwargs) -> None:
        self._send("error", data={"message": message, **kwargs})

    def push_heartbeat(self) -> None:
        self._send("heartbeat")

    def push_snapshot(self, date: str, signal_count: int = 0,
                      buy_count: int = 0, sell_count: int = 0,
                      daily_return_pct: Optional[float] = None,
                      balance: Optional[float] = None,
                      **kwargs) -> None:
        if not self.url:
            return
        try:
            httpx.post(
                f"{self.url}/api/snapshot/{self.app_id}",
                json={
                    "date": date,
                    "signal_count": signal_count,
                    "buy_count": buy_count,
                    "sell_count": sell_count,
                    "daily_return_pct": daily_return_pct,
                    "balance": balance,
                    "raw_json": kwargs or None,
                },
                headers={"X-Hub-Secret": self.secret},
                timeout=10.0,
            )
        except Exception:
            pass
