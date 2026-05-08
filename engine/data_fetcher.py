"""네이버 금융 기반 일봉 데이터 수집기 (engine/data_fetcher.py).

pykrx 가 빈 응답을 반환하는 문제를 회피하기 위한 대체 데이터 소스.
KRX pykrx → naver finance HTML 스크래핑 (시가총액 상위 페이지) 으로 교체.

URL: https://finance.naver.com/sise/sise_market_sum.naver?sosok={0|1}&page={N}
       sosok = 0 → KOSPI, 1 → KOSDAQ
       page  = 1, 2, 3 …  (50개/페이지)

수집 컬럼 (StockData 매핑):
    code         : <a href="/item/main.naver?code=XXXXXX"> 의 6자리
    name         : 종목명 (anchor text)
    close        : 현재가 (콤마 제거)
    change_pct   : 등락률 (%)
    volume       : 거래량 (주)
    trading_value: close × volume (원)  — 네이버 페이지에 없는 항목, 추정값
    marcap       : 시가총액 (원, 페이지의 "억" 단위 → ×1e8)

설계:
    - urllib + 정규식 (scripts/fetch_naver_supply.py 와 동일 스타일)
    - euc-kr 인코딩, User-Agent 필수
    - 페이지당 0.3s 슬립 (네이버 차단 회피)
    - asyncio 호환을 위해 동기 함수 + asyncio.to_thread 호출 컨벤션
"""

from __future__ import annotations

import logging
import re
import time
import urllib.request
from typing import List, Optional

from engine.models import StockData

logger = logging.getLogger(__name__)

NAVER_LIST_URL = (
    "https://finance.naver.com/sise/sise_market_sum.naver?sosok={sosok}&page={page}"
)
HEADERS = {"User-Agent": "Mozilla/5.0"}
REQUEST_DELAY_SEC = 0.30
ROWS_PER_PAGE = 50

_CODE_RE = re.compile(r'href="[^"]*code=(\d{6})"[^>]*>([^<]+)</a>')
_TR_RE = re.compile(r'<tr[^>]*>(.*?)</tr>', re.DOTALL)
_TD_RE = re.compile(r'<td[^>]*>(.*?)</td>', re.DOTALL)
_TAG_RE = re.compile(r'<[^>]*>')
_NBSP_RE = re.compile(r'&nbsp;|\xa0')


def _clean(html_fragment: str) -> str:
    """HTML 태그 제거 + nbsp 정리 + 좌우 공백 제거."""
    s = _TAG_RE.sub('', html_fragment)
    s = _NBSP_RE.sub(' ', s)
    return s.strip()


def _to_int(s: str) -> int:
    s = s.replace(",", "").replace("+", "").strip()
    if not s or s in {"-", "N/A"}:
        return 0
    try:
        return int(s)
    except ValueError:
        try:
            return int(float(s))
        except ValueError:
            return 0


def _to_float(s: str) -> float:
    s = s.replace(",", "").replace("+", "").replace("%", "").strip()
    if not s or s in {"-", "N/A"}:
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def _parse_page(html: str, market: str) -> List[StockData]:
    """단일 시세 페이지 HTML 파싱.

    type_2 테이블의 각 행을 분해해 StockData 로 매핑.
    페이지 컬럼(시가총액 상위):
        N | 종목명 | 현재가 | 전일비 | 등락률 | 액면가 | 시가총액(억) |
        상장주식수 | 외국인비율 | 거래량 | PER | ROE
    """
    out: List[StockData] = []
    for tr_html in _TR_RE.findall(html):
        m = _CODE_RE.search(tr_html)
        if not m:
            continue
        code, name = m.group(1), _clean(m.group(2))
        cells = [_clean(td) for td in _TD_RE.findall(tr_html)]
        # 비어있는 셀 제거 후 인덱스 매핑 (네이버 페이지는 종종 빈 td 가 끼어있음)
        nums = [c for c in cells if c and c not in {name}]
        # nums[0]=N, [1]=현재가, [2]=전일비, [3]=등락률, [4]=액면가,
        # [5]=시가총액(억), [6]=상장주식수, [7]=외국인비율, [8]=거래량
        if len(nums) < 9:
            continue
        close = _to_float(nums[1])
        change_pct = _to_float(nums[3])
        marcap_eok = _to_int(nums[5])              # 억 원
        volume = _to_int(nums[8])
        trading_value = int(close * volume)        # 추정 거래대금 (원)

        if close <= 0:
            continue

        out.append(StockData(
            code=code,
            name=name,
            market=market,
            sector="",
            close=close,
            change_pct=change_pct,
            trading_value=trading_value,
            volume=volume,
            marcap=marcap_eok * 100_000_000,
        ))
    return out


def _fetch_page(market: str, page: int) -> List[StockData]:
    """단일 페이지 HTTP 호출 + 파싱."""
    sosok = "0" if market.upper() == "KOSPI" else "1"
    url = NAVER_LIST_URL.format(sosok=sosok, page=page)
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("euc-kr", errors="ignore")
    except Exception as e:
        logger.warning(f"[NaverFetcher] {market} page={page} HTTP 실패: {e}")
        return []
    return _parse_page(html, market.upper())


def naver_top_gainers(
    market: str = "KOSPI",
    top_n: int = 30,
    *,
    pages: int = 4,
    min_trading_value: int = 5_000_000_000,
    max_change_pct: float = 15.0,
    min_close_price: int = 1_000,
) -> List[StockData]:
    """시가총액 상위 페이지에서 후보를 모은 뒤 등락률 내림차순 top_n.

    필터 (KRXCollector.get_top_gainers 와 동일 의미):
        * 거래대금 ≥ min_trading_value
        * 등락률 ≤ max_change_pct (당일 급등 제외)
        * 종가 ≥ min_close_price (동전주 제외)

    Args:
        pages: 시가총액 상위 페이지 수 (기본 4 → 약 200 종목 풀)
    """
    pool: List[StockData] = []
    for page in range(1, pages + 1):
        rows = _fetch_page(market, page)
        if not rows:
            break
        pool.extend(rows)
        time.sleep(REQUEST_DELAY_SEC)

    if not pool:
        logger.warning(f"[NaverFetcher] {market} 풀이 비어있음")
        return []

    filtered = [
        s for s in pool
        if s.trading_value >= min_trading_value
        and s.change_pct <= max_change_pct
        and s.close >= min_close_price
    ]
    filtered.sort(key=lambda s: s.change_pct, reverse=True)
    logger.info(
        f"[NaverFetcher] {market} 풀 {len(pool)} → 필터 통과 {len(filtered)} → top_n {top_n}"
    )
    return filtered[:top_n]
