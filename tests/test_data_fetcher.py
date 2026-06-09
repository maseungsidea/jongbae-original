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


# ETF 행이 포함된 샘플 페이지 — ETF 필터 및 max_marcap 회귀 테스트용.
# 069500(KODEX 200): 시총 100,000억 = 10조, 종가 40,000, 거래대금 충분
# 000660(SK하이닉스): 시총 1,500,000억 = 150조, 종가 200,000
# 035720(카카오): 시총 30,000억 = 3조, 종가 50,000 (max_marcap 경계 테스트용)
SAMPLE_PAGE_HTML_WITH_ETF = """
<table class="type_2">
  <tr><th>N</th><th>종목명</th><th>현재가</th><th>전일비</th><th>등락률</th>
      <th>액면가</th><th>시가총액</th><th>상장주식수</th><th>외국인비율</th>
      <th>거래량</th><th>PER</th><th>ROE</th></tr>
  <tr></tr>
  <tr>
    <td>1</td>
    <td><a href="/item/main.naver?code=069500">KODEX 200</a></td>
    <td>40,000</td>
    <td>+100</td>
    <td>+0.25%</td>
    <td>100</td>
    <td>100,000</td>
    <td>250,000,000</td>
    <td>30.00</td>
    <td>5,000,000</td>
    <td>15.0</td>
    <td>5.0</td>
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
    <td><a href="/item/main.naver?code=035720">카카오</a></td>
    <td>50,000</td>
    <td>+500</td>
    <td>+1.00%</td>
    <td>100</td>
    <td>30,000</td>
    <td>888,000,000</td>
    <td>20.00</td>
    <td>3,000,000</td>
    <td>18.0</td>
    <td>8.0</td>
  </tr>
</table>
"""


def _make_fresh_pykrx():
    """pykrx 교차검증 게이트를 통과시키는 non-empty DataFrame mock."""
    m = MagicMock()
    m.empty = False
    return m


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


class TestEtfFilterRegression:
    """ETF 누출 방지 회귀 테스트 — naver_top_gainers 와 naver_all_liquid_stocks 양 경로 커버."""

    def _run_top_gainers(self, **kwargs):
        fresh = _make_fresh_pykrx()
        with patch(
            "engine.data_fetcher.urllib.request.urlopen",
            side_effect=lambda *a, **k: _fake_urlopen(SAMPLE_PAGE_HTML_WITH_ETF),
        ), patch(
            "pykrx.stock.get_market_ohlcv_by_date", return_value=fresh,
        ):
            return data_fetcher.naver_top_gainers(
                "KOSPI", top_n=10, pages=1,
                min_trading_value=1_000_000_000,
                max_change_pct=15.0,
                min_close_price=1_000,
                **kwargs,
            )

    def _run_all_liquid(self, **kwargs):
        fresh = _make_fresh_pykrx()
        with patch(
            "engine.data_fetcher.urllib.request.urlopen",
            side_effect=lambda *a, **k: _fake_urlopen(SAMPLE_PAGE_HTML_WITH_ETF),
        ), patch(
            "pykrx.stock.get_market_ohlcv_by_date", return_value=fresh,
        ):
            return data_fetcher.naver_all_liquid_stocks(
                "KOSPI", pages=1,
                min_trading_value=1_000_000_000,
                max_change_pct=15.0,
                min_close_price=1_000,
                **kwargs,
            )

    # (a) naver_top_gainers 에서 KODEX 200 제외 — 이 경로는 이전에 필터 없음 (회귀 잠금)
    def test_top_gainers_excludes_etf(self):
        rs = self._run_top_gainers()
        codes = [r.code for r in rs]
        assert "069500" not in codes, "KODEX 200(ETF)이 top_gainers 에 누출됨"
        assert "000660" in codes, "SK하이닉스가 잘못 제외됨"

    # (b) naver_all_liquid_stocks 에서도 KODEX 200 제외
    def test_all_liquid_excludes_etf(self):
        rs = self._run_all_liquid()
        codes = [r.code for r in rs]
        assert "069500" not in codes, "KODEX 200(ETF)이 all_liquid 에 누출됨"
        assert "000660" in codes, "SK하이닉스가 잘못 제외됨"

    # (c) max_marcap: None 이면 모든 비-ETF 종목 포함
    def test_max_marcap_none_includes_all_non_etf(self):
        rs = self._run_top_gainers(max_marcap=None)
        codes = [r.code for r in rs]
        # SK하이닉스(시총 150조), 카카오(시총 3조) 모두 포함
        assert "000660" in codes
        assert "035720" in codes
        assert "069500" not in codes  # ETF는 여전히 제외

    # (c) max_marcap: 설정 시 초과 종목 제외 — top_gainers
    def test_max_marcap_excludes_large_cap_top_gainers(self):
        # SK하이닉스 시총 150조 = 150_000_000_000_000
        # 카카오 시총 3조 = 3_000_000_000_000
        # max_marcap = 5조 → SK하이닉스 제외, 카카오 통과
        rs = self._run_top_gainers(max_marcap=5_000_000_000_000)
        codes = [r.code for r in rs]
        assert "000660" not in codes, "SK하이닉스(150조)가 max_marcap=5조 제한에서 누출됨"
        assert "035720" in codes, "카카오(3조)가 max_marcap=5조 에서 잘못 제외됨"

    # (c) max_marcap: 설정 시 초과 종목 제외 — all_liquid
    def test_max_marcap_excludes_large_cap_all_liquid(self):
        rs = self._run_all_liquid(max_marcap=5_000_000_000_000)
        codes = [r.code for r in rs]
        assert "000660" not in codes, "SK하이닉스(150조)가 max_marcap=5조 제한에서 누출됨"
        assert "035720" in codes, "카카오(3조)가 max_marcap=5조 에서 잘못 제외됨"

    # (d) 이름패턴 오탐 잠금 — 운용사 상호로 시작하는 보통주는 ETF 로 오인되면 안 된다.
    #     (미래에셋증권/한국투자증권/파워로직스 등이 유니버스에서 빠지면 추천 빈도 KPI 훼손)
    def test_etf_pattern_no_false_positive_on_common_stocks(self):
        for nm in ("미래에셋증권", "미래에셋생명", "한국투자증권", "파워로직스", "파워넷"):
            assert not data_fetcher._is_etf_like(nm), f"보통주 {nm} 가 ETF 로 오탐됨"

    # (d) 진짜 ETF/ETN 은 계속 제외돼야 한다 (오탐 수정이 정탐을 깨지 않았는지).
    def test_etf_pattern_still_catches_real_etfs(self):
        for nm in ("KODEX 200", "TIGER 미국S&P500", "ACE 국고채10년",
                   "ARIRANG 고배당주", "삼성 레버리지 WTI원유 선물 ETN",
                   "신한 인버스 2X 나스닥 ETN", "맥쿼리인프라리츠"):
            assert data_fetcher._is_etf_like(nm), f"실제 ETF/ETN/리츠 {nm} 가 제외되지 않음"
