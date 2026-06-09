"""engine/data_fetcher.py 단위 테스트.

네이버 페이지 HTTP 호출은 mock — 실제 네트워크 안 탐.
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from engine import data_fetcher


SAMPLE_PAGE_HTML = """
<table class="type_2">
  <tr><th>N</th><th>종목명</th><th>현재가</th><th>전일비</th><th>등락률</th>
      <th>액면가</th><th>시가총액</th><th>상장주식수</th><th>외국인비율</th>
      <th>거래량</th><th>PER</th><th>ROE</th></tr>
  <tr></tr>
  <tr>
    <td>1</td>
    <td><a href="/item/main.naver?code=005930">삼성전자</a></td>
    <td>70,000</td>
    <td>+1,000</td>
    <td>+1.45%</td>
    <td>100</td>
    <td>4,200,000</td>
    <td>5,969,782,550</td>
    <td>54.32</td>
    <td>10,000,000</td>
    <td>15.2</td>
    <td>10.5</td>
  </tr>
  <tr>
    <td>2</td>
    <td><a href="/item/main.naver?code=000660">SK하이닉스</a></td>
    <td>200,000</td>
    <td>+5,000</td>
    <td>+2.50%</td>
    <td>5,000</td>
    <td>1,500,000</td>
    <td>728,002,365</td>
    <td>50.10</td>
    <td>2,500,000</td>
    <td>20.0</td>
    <td>12.0</td>
  </tr>
  <tr>
    <td>3</td>
    <td><a href="/item/main.naver?code=900900">동전주</a></td>
    <td>800</td>
    <td>+10</td>
    <td>+1.20%</td>
    <td>500</td>
    <td>5,000</td>
    <td>1,000,000</td>
    <td>5.00</td>
    <td>500,000</td>
    <td>-</td>
    <td>-</td>
  </tr>
  <tr>
    <td>4</td>
    <td><a href="/item/main.naver?code=900901">급등주</a></td>
    <td>50,000</td>
    <td>+15,000</td>
    <td>+30.00%</td>
    <td>500</td>
    <td>10,000</td>
    <td>1,000,000</td>
    <td>5.00</td>
    <td>1,000,000</td>
    <td>-</td>
    <td>-</td>
  </tr>
</table>
"""


def _fake_urlopen(html: str):
    """`urllib.request.urlopen(...)` 컨텍스트 매니저 mock."""
    resp = MagicMock()
    resp.read.return_value = html.encode("euc-kr", errors="ignore")
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=resp)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


class TestParsePage:
    def test_parses_rows(self):
        rows = data_fetcher._parse_page(SAMPLE_PAGE_HTML, "KOSPI")
        codes = [r.code for r in rows]
        assert "005930" in codes
        assert "000660" in codes
        ss = next(r for r in rows if r.code == "005930")
        assert ss.name == "삼성전자"
        assert ss.close == 70000.0
        assert ss.change_pct == 1.45
        # 거래대금 = 70000 * 10000000 = 700,000,000,000 = 7000억
        assert ss.trading_value == 700_000_000_000
        # 시총 4,200,000억 → 4.2조 * 1e8 = 4.2e14
        assert ss.marcap == 420_000_000_000_000

    def test_skips_rows_without_code(self):
        rows = data_fetcher._parse_page(SAMPLE_PAGE_HTML, "KOSPI")
        assert all(r.code.isdigit() for r in rows)


class TestNaverTopGainers:
    def test_filters_low_close_and_high_change(self):
        # 3차 신선도 gate(pykrx 교차검증, data_fetcher.py:239~)는 오늘 거래 데이터가 없으면
        # fail-closed 로 빈 결과를 반환한다. 여기선 필터 로직만 검증하므로 교차검증을 통과시킨다.
        _fresh = MagicMock()
        _fresh.empty = False
        with patch(
            "engine.data_fetcher.urllib.request.urlopen",
            side_effect=lambda *a, **k: _fake_urlopen(SAMPLE_PAGE_HTML),
        ), patch(
            "pykrx.stock.get_market_ohlcv_by_date", return_value=_fresh,
        ):
            rs = data_fetcher.naver_top_gainers(
                "KOSPI", top_n=10, pages=1,
                min_trading_value=10_000_000_000,
                max_change_pct=15.0,
                min_close_price=1_000,
            )
        codes = [r.code for r in rs]
        assert "005930" in codes
        assert "000660" in codes
        # 동전주 종가 800 → min_close_price 1000 미달 → 제외
        assert "900900" not in codes
        # 급등주 등락률 30% → max_change_pct 15 초과 → 제외
        assert "900901" not in codes

    def test_sorts_by_change_pct_desc(self):
        with patch(
            "engine.data_fetcher.urllib.request.urlopen",
            side_effect=lambda *a, **k: _fake_urlopen(SAMPLE_PAGE_HTML),
        ):
            rs = data_fetcher.naver_top_gainers(
                "KOSPI", top_n=10, pages=1,
                min_trading_value=1_000_000_000,
                max_change_pct=20.0,
                min_close_price=500,
            )
        # 정렬: 등락률 DESC
        change_pcts = [r.change_pct for r in rs]
        assert change_pcts == sorted(change_pcts, reverse=True)

    def test_empty_pool_returns_empty(self):
        with patch(
            "engine.data_fetcher.urllib.request.urlopen",
            side_effect=lambda *a, **k: _fake_urlopen("<html>no table</html>"),
        ):
            rs = data_fetcher.naver_top_gainers("KOSPI", top_n=10, pages=1)
        assert rs == []
