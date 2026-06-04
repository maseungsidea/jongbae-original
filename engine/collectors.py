"""
데이터 수집 레이어 (engine/collectors.py)

KRX와 네이버/다음 뉴스에서 데이터를 비동기적으로 수집합니다.

- KRXCollector   : pykrx 기반 주가·수급 데이터 수집 (async context manager)
- EnhancedNewsCollector : 네이버 증권 뉴스 크롤링 (async context manager)

설계 의도:
  pykrx는 동기 라이브러리이지만, I/O 병목을 줄이기 위해
  asyncio.to_thread() 로 스레드 풀에서 실행합니다.
  aiohttp 세션을 통한 HTTP 요청은 완전 비동기로 처리합니다.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta
from typing import List, Optional
from urllib.parse import quote

import aiohttp
from bs4 import BeautifulSoup

from engine.config import SignalConfig
from engine.models import ChartData, NewsItem, StockData, SupplyData

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────
# KRXCollector
# ─────────────────────────────────────────

class KRXCollector:
    """
    pykrx 기반 KRX 데이터 수집기.

    async with KRXCollector(config) as collector: 형태로 사용합니다.
    내부적으로 aiohttp.ClientSession 을 관리합니다.

    주의: pykrx API는 KRX 웹사이트를 직접 파싱하므로
         과도한 요청은 IP 차단을 유발할 수 있습니다.
         요청 간격(request_delay_sec)을 반드시 준수하세요.
    """

    # pykrx 호출 사이의 최소 대기 시간 (초)
    REQUEST_DELAY_SEC: float = 0.3

    def __init__(self, config: SignalConfig):
        self.config = config
        self._session: Optional[aiohttp.ClientSession] = None

    # ── Context Manager ───────────────────────

    async def __aenter__(self) -> "KRXCollector":
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30)
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    # ── 공개 메서드 ───────────────────────────

    async def get_top_gainers(
        self, market: str = "KOSPI", top_n: int = 30
    ) -> List[StockData]:
        """
        당일 등락률 상위 종목 조회.

        2026-05 부터 기본 소스를 pykrx → 네이버 금융(`engine.data_fetcher`) 으로
        교체했다. KRX 통계 페이지가 빈 응답을 자주 던지는 이슈 회피.

        환경변수 ``JONGGA_DATA_SOURCE`` 로 강제 지정 가능 (``naver`` | ``pykrx``).
        기본값은 ``naver``.
        """
        import os
        source = os.getenv("JONGGA_DATA_SOURCE", "naver").lower()
        if source == "pykrx":
            return await self._top_gainers_pykrx(market, top_n)
        return await self._top_gainers_naver(market, top_n)

    async def get_all_liquid_stocks(self, market: str = "KOSPI") -> List[StockData]:
        """시가총액 상위 전체 스캔 — 급등주 bias 없음.

        change_pct 랭킹 없이 TV ≥ Grade B 기준을 통과하는 종목 전체를 반환.
        naver_all_liquid_stocks() 를 비동기로 래핑.
        """
        from engine.config import Grade
        from engine.data_fetcher import naver_all_liquid_stocks
        gc_b = self.config.get_grade_config(Grade.B)
        try:
            return await asyncio.to_thread(
                naver_all_liquid_stocks,
                market,
                min_trading_value=gc_b.min_trading_value,
                max_change_pct=self.config.max_change_pct,
                min_close_price=self.config.min_close_price,
            )
        except Exception as e:
            logger.error(f"[KRXCollector] get_all_liquid_stocks({market}) 오류: {e}")
            return []

    async def _top_gainers_naver(
        self, market: str, top_n: int
    ) -> List[StockData]:
        """네이버 금융 시가총액 상위 페이지 → 필터 → 등락률 내림차순 top_n."""
        from engine.data_fetcher import naver_top_gainers
        try:
            return await asyncio.to_thread(
                naver_top_gainers,
                market=market,
                top_n=top_n,
                min_trading_value=self.config.min_trading_value,
                max_change_pct=self.config.max_change_pct,
                min_close_price=self.config.min_close_price,
            )
        except Exception as e:
            logger.error(f"[KRXCollector] naver get_top_gainers 오류: {e}")
            return []

    async def _top_gainers_pykrx(
        self, market: str, top_n: int
    ) -> List[StockData]:
        """기존 pykrx 경로 (백업용)."""
        try:
            import pykrx.stock as stock

            today_str = date.today().strftime("%Y%m%d")
            df = await asyncio.to_thread(
                stock.get_market_ohlcv_by_ticker, today_str, market=market
            )
            if df is None or df.empty:
                logger.warning(f"[KRXCollector] pykrx {market} 데이터 없음")
                return []
            df = df[df["거래대금"] >= self.config.min_trading_value]
            df = df[df["등락률"] <= self.config.max_change_pct]
            df = df[df["종가"] >= self.config.min_close_price]
            df = df.sort_values("등락률", ascending=False).head(top_n)

            results: List[StockData] = []
            for ticker, row in df.iterrows():
                name = await asyncio.to_thread(stock.get_market_ticker_name, ticker)
                await asyncio.sleep(self.REQUEST_DELAY_SEC)
                results.append(StockData(
                    code=str(ticker), name=name, market=market, sector="",
                    close=float(row.get("종가", 0)),
                    change_pct=float(row.get("등락률", 0)),
                    trading_value=int(row.get("거래대금", 0)),
                    volume=int(row.get("거래량", 0)),
                    marcap=int(row.get("시가총액", 0)) if "시가총액" in row else 0,
                ))
            return results
        except Exception as e:
            logger.error(f"[KRXCollector] pykrx get_top_gainers 오류: {e}")
            return []

    async def get_stock_detail(self, code: str) -> Optional[StockData]:
        """
        단일 종목 상세 데이터 조회.

        Args:
            code: 6자리 종목코드

        Returns:
            StockData (데이터가 없으면 None)
        """
        try:
            import pykrx.stock as stock

            today_str = date.today().strftime("%Y%m%d")
            df = await asyncio.to_thread(
                stock.get_market_ohlcv_by_date, today_str, today_str, code
            )

            if df is None or df.empty:
                return None

            row = df.iloc[-1]
            name = await asyncio.to_thread(stock.get_market_ticker_name, code)
            await asyncio.sleep(self.REQUEST_DELAY_SEC)

            # 52주 최고가
            start_52w = (date.today() - timedelta(weeks=52)).strftime("%Y%m%d")
            df_52w = await asyncio.to_thread(
                stock.get_market_ohlcv_by_date, start_52w, today_str, code
            )
            high_52w = float(df_52w["고가"].max()) if df_52w is not None and not df_52w.empty else None

            return StockData(
                code=code,
                name=name,
                market="",   # 시장 구분은 목록 수집 시 파악
                sector="",
                close=float(row.get("종가", 0)),
                change_pct=float(row.get("등락률", 0)),
                trading_value=int(row.get("거래대금", 0)),
                volume=int(row.get("거래량", 0)),
                marcap=0,
                high_52w=high_52w,
            )

        except Exception as e:
            logger.error(f"[KRXCollector] get_stock_detail({code}) 오류: {e}")
            return None

    async def get_chart_data(self, code: str, days: int = 90) -> List[ChartData]:
        """
        일봉 OHLCV 데이터 조회.

        Args:
            code: 6자리 종목코드
            days: 조회 기간 (일)

        Returns:
            날짜 오름차순 정렬된 ChartData 리스트
        """
        try:
            import pykrx.stock as stock

            end = date.today()
            start = end - timedelta(days=days)
            df = await asyncio.to_thread(
                stock.get_market_ohlcv_by_date,
                start.strftime("%Y%m%d"),
                end.strftime("%Y%m%d"),
                code,
            )
            await asyncio.sleep(self.REQUEST_DELAY_SEC)

            if df is None or df.empty:
                return []

            return [
                ChartData(
                    date=str(idx.date()),
                    open=float(row["시가"]),
                    high=float(row["고가"]),
                    low=float(row["저가"]),
                    close=float(row["종가"]),
                    volume=int(row["거래량"]),
                )
                for idx, row in df.iterrows()
            ]

        except Exception as e:
            logger.error(f"[KRXCollector] get_chart_data({code}) 오류: {e}")
            return []

    async def get_supply_data(self, code: str) -> Optional[SupplyData]:
        """
        외인/기관 5일 누적 순매수 조회.

        Args:
            code: 6자리 종목코드

        Returns:
            SupplyData (데이터 없으면 None)
        """
        try:
            import pykrx.stock as stock

            end = date.today()
            start = end - timedelta(days=self.config.supply_lookback_days + 3)  # 주말 여유분

            # KOSPI / KOSDAQ 양쪽 모두 조회 (종목코드는 시장간 unique)
            for market in ("KOSPI", "KOSDAQ"):
                df = await asyncio.to_thread(
                    stock.get_market_net_purchases_of_equities_by_ticker,
                    start.strftime("%Y%m%d"),
                    end.strftime("%Y%m%d"),
                    market,
                )
                await asyncio.sleep(self.REQUEST_DELAY_SEC)
                if df is not None and not df.empty and code in df.index:
                    row = df.loc[code]
                    return SupplyData(
                        foreign_buy_5d=int(row.get("외국인", 0)),
                        inst_buy_5d=int(row.get("기관합계", 0)),
                    )

            return SupplyData()  # 어느 시장에서도 발견 못하면 기본값

        except Exception as e:
            logger.error(f"[KRXCollector] get_supply_data({code}) 오류: {e}")
            return SupplyData()


# ─────────────────────────────────────────
# EnhancedNewsCollector
# ─────────────────────────────────────────

class EnhancedNewsCollector:
    """
    네이버 증권 뉴스 크롤링 수집기.

    네이버 금융(finance.naver.com)의 종목별 뉴스 페이지를 파싱합니다.
    robots.txt를 준수하며, 요청 사이에 딜레이를 적용합니다.
    """

    NAVER_NEWS_URL = "https://finance.naver.com/item/news_news.naver?code={code}&page=1"

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": "https://finance.naver.com",
    }

    REQUEST_DELAY_SEC: float = 0.5

    def __init__(self, config: SignalConfig):
        self.config = config
        self._session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self) -> "EnhancedNewsCollector":
        self._session = aiohttp.ClientSession(
            headers=self.HEADERS,
            timeout=aiohttp.ClientTimeout(total=15),
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    async def get_stock_news(
        self, code: str, limit: int = 5, name: str = ""
    ) -> List[NewsItem]:
        """
        종목별 최신 뉴스 수집.

        Args:
            code: 6자리 종목코드
            limit: 수집할 최대 뉴스 개수
            name: 종목명 (로깅용)

        Returns:
            NewsItem 리스트 (최대 limit 개)
        """
        if self._session is None:
            logger.error("[NewsCollector] session이 초기화되지 않았습니다. async with 블록 내에서 사용하세요.")
            return []

        url = self.NAVER_NEWS_URL.format(code=code)
        try:
            async with self._session.get(url) as resp:
                if resp.status != 200:
                    logger.warning(f"[NewsCollector] {name}({code}) 뉴스 HTTP {resp.status}")
                    return []
                html = await resp.text(encoding="euc-kr", errors="replace")

            await asyncio.sleep(self.REQUEST_DELAY_SEC)
            return self._parse_news(html, limit)

        except asyncio.TimeoutError:
            logger.warning(f"[NewsCollector] {name}({code}) 타임아웃")
            return []
        except Exception as e:
            logger.error(f"[NewsCollector] {name}({code}) 오류: {e}")
            return []

    def _parse_news(self, html: str, limit: int) -> List[NewsItem]:
        """
        네이버 증권 뉴스 HTML 파싱.
        DOM 구조 변경 시 이 메서드만 수정하면 됩니다.
        """
        soup = BeautifulSoup(html, "lxml")
        news_items: List[NewsItem] = []

        # 네이버 증권 뉴스 테이블 파싱 (2024년 기준 DOM 구조)
        rows = soup.select("table.type5 tr")
        for row in rows:
            title_tag = row.select_one("td.title a")
            source_tag = row.select_one("td.info")
            date_tag = row.select_one("td.date")

            if not title_tag:
                continue

            title = title_tag.get_text(strip=True)
            href = title_tag.get("href", "")
            url = f"https://finance.naver.com{href}" if href.startswith("/") else href
            source = source_tag.get_text(strip=True) if source_tag else "네이버 증권"
            date_str = date_tag.get_text(strip=True) if date_tag else ""

            # 짧은 제목이나 광고성 기사 필터
            if len(title) < 5:
                continue

            published_at: Optional[datetime] = None
            try:
                # 네이버 날짜 형식: "2024.01.15 09:30" 또는 "10:30"
                if "." in date_str:
                    published_at = datetime.strptime(date_str, "%Y.%m.%d %H:%M")
                elif ":" in date_str:
                    today = date.today()
                    t = datetime.strptime(date_str, "%H:%M")
                    published_at = t.replace(year=today.year, month=today.month, day=today.day)
            except ValueError:
                pass

            news_items.append(NewsItem(
                title=title,
                summary="",     # 상세 크롤링 없이 제목만 수집 (LLM 분석 비용 절감)
                source=source,
                url=url,
                published_at=published_at,
            ))

            if len(news_items) >= limit:
                break

        return news_items
