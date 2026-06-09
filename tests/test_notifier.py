"""utils/notifier.py 단위 테스트.

실제 Telegram API 는 호출하지 않는다 — urllib.request.urlopen 을 모두 mock.
"""
from __future__ import annotations

import json
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from utils import notifier


@pytest.fixture
def env_enabled(monkeypatch):
    monkeypatch.setenv("TELEGRAM_TOKEN", "test_token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
    monkeypatch.delenv("JONGGA_NOTIFY", raising=False)
    # 발신은 fail-closed 활성화 게이트가 ON 이어야 한다 (EV+2% 입증 후 운영 상태 모사).
    monkeypatch.setenv("JONGGA_SEND_ACTIVATED", "1")


@pytest.fixture
def env_disabled(monkeypatch):
    monkeypatch.setenv("TELEGRAM_TOKEN", "test_token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
    monkeypatch.setenv("JONGGA_SEND_ACTIVATED", "1")  # 활성화돼 있어도
    monkeypatch.setenv("JONGGA_NOTIFY", "0")           # kill-switch 가 우선 차단


@pytest.fixture
def env_no_creds(monkeypatch):
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)


def _ok_response() -> MagicMock:
    """Telegram API 성공 응답을 흉내내는 컨텍스트 매니저."""
    resp = MagicMock()
    resp.status = 200
    resp.read.return_value = json.dumps({"ok": True, "result": {}}).encode()
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=resp)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


def _http_error_response(status: int = 400) -> MagicMock:
    resp = MagicMock()
    resp.status = status
    resp.read.return_value = b'{"ok":false,"description":"bad"}'
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=resp)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


class TestEscapeHtml:
    def test_basic(self):
        assert notifier._escape_html("a & b") == "a &amp; b"

    def test_tags(self):
        assert notifier._escape_html("<script>") == "&lt;script&gt;"


class TestSendMessage:
    def test_disabled_via_env(self, env_disabled):
        with patch("utils.notifier.urllib.request.urlopen") as m:
            assert notifier.send_message("hi") is False
            m.assert_not_called()

    def test_fail_closed_when_not_activated(self, monkeypatch):
        """BLOCKER 회귀잠금: 자격증명이 있어도 JONGGA_SEND_ACTIVATED 미설정이면 발신 금지.

        EV +2% 필요조건 미입증 상태(=활성화 게이트 OFF, 기본값)에서는 절대 발신하지 않는다.
        배포 환경에 env 를 빠뜨려도 fail-closed 로 침묵해야 한다 (CLAUDE.md KPI BLOCKER).
        """
        monkeypatch.setenv("TELEGRAM_TOKEN", "test_token")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
        monkeypatch.delenv("JONGGA_NOTIFY", raising=False)        # kill-switch 미설정(기본 on)
        monkeypatch.delenv("JONGGA_SEND_ACTIVATED", raising=False)  # 활성화 미설정 → fail-closed
        with patch("utils.notifier.urllib.request.urlopen") as m:
            assert notifier.send_message("hi") is False
            m.assert_not_called()

    def test_no_credentials(self, env_no_creds):
        with patch("utils.notifier.urllib.request.urlopen") as m:
            assert notifier.send_message("hi") is False
            m.assert_not_called()

    def test_success(self, env_enabled):
        with patch("utils.notifier.urllib.request.urlopen", return_value=_ok_response()) as m:
            assert notifier.send_message("hi") is True
            m.assert_called_once()
            req = m.call_args[0][0]
            assert "/bot" in req.full_url
            assert b"chat_id=12345" in req.data

    def test_http_error_returns_false(self, env_enabled):
        with patch("utils.notifier.urllib.request.urlopen", return_value=_http_error_response(500)):
            assert notifier.send_message("hi") is False

    def test_network_exception_swallowed(self, env_enabled):
        with patch("utils.notifier.urllib.request.urlopen", side_effect=OSError("conn refused")):
            # 네트워크 실패가 운영 흐름을 죽이면 안 됨
            assert notifier.send_message("hi") is False


class TestNotifySignal:
    def test_with_full_prices(self, env_enabled):
        with patch("utils.notifier.urllib.request.urlopen", return_value=_ok_response()) as m:
            notifier.notify_signal(
                ticker="005930", name="삼성전자", grade="A", score=9,
                entry_price=70000, stop_price=67900, target_price=75600,
                market="KOSPI", trading_value=600_000_000_000,
            )
            req = m.call_args[0][0]
            text = req.data.decode()
            assert "005930" in text
            # 한글은 percent-encoded 되므로 escape 후 안 깨지는지만 검증
            assert "70%2C000" in text or "70,000" in text  # 진입가
            assert "%EC%82%BC%EC%84%B1" in text  # "삼성" url-encoded

    def test_omits_stop_target_when_zero(self, env_enabled):
        """scorer 단계 알림 — stop/target 없는 케이스."""
        with patch("utils.notifier.urllib.request.urlopen", return_value=_ok_response()) as m:
            notifier.notify_signal(
                ticker="005930", name="Samsung", grade="A", score=9,
                entry_price=70000,
            )
            text = m.call_args[0][0].data.decode()
            assert "%EC%86%90%EC%A0%88" not in text  # "손절" 미포함
            assert "70%2C000" in text or "70,000" in text  # 현재가 표시


class TestNotifyOrder:
    def test_buy_success(self, env_enabled):
        with patch("utils.notifier.urllib.request.urlopen", return_value=_ok_response()) as m:
            assert notifier.notify_order(
                side="buy", ticker="005930", quantity=10, price=70000,
                ok=True, odno="0000123456",
            ) is True
            text = m.call_args[0][0].data.decode()
            assert "0000123456" in text

    def test_sell_failure(self, env_enabled):
        with patch("utils.notifier.urllib.request.urlopen", return_value=_ok_response()) as m:
            notifier.notify_order(
                side="sell", ticker="005930", quantity=5, price=70000,
                ok=False, msg="잔고 부족",
            )
            text = m.call_args[0][0].data.decode()
            # "실패" 포함 확인 (url-encoded)
            assert "%EC%8B%A4%ED%8C%A8" in text


class TestNotifyTodayRecommendations:
    @pytest.fixture(autouse=True)
    def _trading_day(self, monkeypatch):
        # 4차 gate(is_trading_day)는 발송 직전 휴장일 재확인용 — 해피패스 테스트에선
        # 거래일로 고정해 실제 발송 로직을 검증한다. (함수 내부 import 이므로 원본 모듈 패치)
        monkeypatch.setattr("engine.market_utils.is_trading_day", lambda *a, **k: True)

    def test_with_items(self, env_enabled, tmp_path):
        p = tmp_path / "today.json"
        p.write_text(json.dumps({
            "date": "2026-05-08",
            "count": 2,
            "items": [
                {"ticker": "005930", "name": "삼성전자", "grade": "A",
                 "score": 9, "price": 70000, "trading_value": 600_000_000_000},
                {"ticker": "000660", "name": "SK하이닉스", "grade": "B",
                 "score": 7, "price": 200000, "trading_value": 0},
            ],
        }, ensure_ascii=False), encoding="utf-8")
        with patch("utils.notifier.urllib.request.urlopen", return_value=_ok_response()) as m:
            assert notifier.notify_today_recommendations(str(p)) is True
            text = m.call_args[0][0].data.decode()
            # 삼성전자 / SK하이닉스 url-encoded 일부 포함
            assert "%EC%82%BC%EC%84%B1" in text          # "삼성"
            assert "005930" in text and "000660" in text
            assert "70%2C000" in text or "70,000" in text

    def test_empty_items(self, env_enabled, tmp_path):
        p = tmp_path / "today.json"
        p.write_text(json.dumps({"date": "2026-05-08", "count": 0, "items": []}),
                     encoding="utf-8")
        with patch("utils.notifier.urllib.request.urlopen", return_value=_ok_response()) as m:
            assert notifier.notify_today_recommendations(str(p)) is True
            text = m.call_args[0][0].data.decode()
            assert "%EC%97%86%EC%9D%8C" in text  # "없음"

    def test_missing_file(self, env_enabled, tmp_path):
        with patch("utils.notifier.urllib.request.urlopen") as m:
            assert notifier.notify_today_recommendations(str(tmp_path / "nope.json")) is False
            m.assert_not_called()

    def test_near_miss_section(self, env_enabled, tmp_path):
        rec = tmp_path / "today.json"
        rec.write_text(json.dumps({
            "date": "2026-05-08", "count": 0, "items": [],
        }), encoding="utf-8")
        cand = tmp_path / "candidates.json"
        cand.write_text(json.dumps({
            "date": "2026-05-08",
            "rejected": [
                {"ticker": "001440", "name": "대한전선", "score": 4,
                 "change_pct": 12.79, "trading_value": 1_463_100_000_000,
                 "reasons": ["낮은 점수(4점, B등급 6점 필요)", "변동성 수축 부족 (20일 BB폭 > 3%)"]},
                {"ticker": "000990", "name": "DB하이텍", "score": 4,
                 "change_pct": 6.73, "trading_value": 153_500_000_000,
                 "reasons": ["낮은 점수(4점, B등급 6점 필요)", "변동성 수축 부족 (20일 BB폭 > 3%)"]},
            ],
        }, ensure_ascii=False), encoding="utf-8")
        with patch("utils.notifier.urllib.request.urlopen", return_value=_ok_response()) as m:
            assert notifier.notify_today_recommendations(str(rec), str(cand)) is True
            text = m.call_args[0][0].data.decode()
            # 헤더 "아깝게 탈락" url-encoded
            assert "%EC%95%84%EA%B9%9D%EA%B2%8C" in text
            assert "001440" in text and "000990" in text

    def test_near_miss_missing_candidates_ok(self, env_enabled, tmp_path):
        """candidates 파일 없어도 추천 파일만으로 발송된다."""
        rec = tmp_path / "today.json"
        rec.write_text(json.dumps({
            "date": "2026-05-08", "count": 0, "items": [],
        }), encoding="utf-8")
        with patch("utils.notifier.urllib.request.urlopen", return_value=_ok_response()) as m:
            assert notifier.notify_today_recommendations(
                str(rec), str(tmp_path / "missing.json")
            ) is True
            m.assert_called_once()


class TestNotifyError:
    def test_with_exception(self, env_enabled):
        with patch("utils.notifier.urllib.request.urlopen", return_value=_ok_response()) as m:
            err = ValueError("뭔가 잘못됨")
            notifier.notify_error("scheduler.run_vcp_scan", err)
            text = m.call_args[0][0].data.decode()
            assert "ValueError" in text
            assert "scheduler" in text

    def test_disabled_no_call(self, env_disabled):
        with patch("utils.notifier.urllib.request.urlopen") as m:
            notifier.notify_error("ctx", RuntimeError("x"))
            m.assert_not_called()
