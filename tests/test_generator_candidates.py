"""SignalGenerator 후보 트래킹 단위 테스트.

_record_candidate / _build_reject_reasons / save_candidates_to_json 검증.
실제 KRX/네이버/뉴스/LLM 호출은 안 함 (네트워크 무관).
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from engine.generator import SignalGenerator
from engine.config import SignalConfig, Grade
from engine.models import StockData, ScoreDetail, ChecklistDetail


@pytest.fixture
def gen():
    return SignalGenerator(config=SignalConfig(), capital=10_000_000)


def _stock(code, name, close, tv):
    return StockData(
        code=code, name=name, market="KOSPI", sector="",
        close=close, change_pct=2.0, trading_value=tv,
        volume=10000, marcap=1_000_000_000_000,
    )


class TestRecordCandidate:
    def test_init_candidates_empty(self, gen):
        assert gen.candidates == []

    def test_pass_records_no_reasons(self, gen):
        s = _stock("005930", "삼성전자", 70000, 600_000_000_000)
        score = ScoreDetail(news=2, volume=2, chart=2, candle=1, consolidation=1, supply=0)  # 8
        gen._record_candidate(s, score, ChecklistDetail(), Grade.A, passed=True)
        c = gen.candidates[0]
        assert c["passed"] is True
        assert c["grade"] == "A"
        assert c["reasons"] == []
        assert c["score"] == 8

    def test_low_score_reason(self, gen):
        s = _stock("005930", "삼성전자", 70000, 600_000_000_000)
        score = ScoreDetail(news=1, volume=2, chart=1, candle=0, consolidation=0, supply=0)  # 4
        gen._record_candidate(s, score, ChecklistDetail(), Grade.C, passed=False)
        reasons = gen.candidates[0]["reasons"]
        assert any("낮은 점수" in r and "4점" in r for r in reasons)

    def test_low_trading_value_reason(self, gen):
        s = _stock("000660", "SK하이닉스", 200000, 50_000_000_000)  # 500억
        score = ScoreDetail(news=2, volume=2, chart=2, candle=1, consolidation=1, supply=0)  # 8
        gen._record_candidate(s, score, ChecklistDetail(), Grade.C, passed=False)
        reasons = gen.candidates[0]["reasons"]
        assert any("거래대금 미달" in r and "500" in r for r in reasons)

    def test_chart_weak_reason(self, gen):
        s = _stock("005930", "삼성전자", 70000, 600_000_000_000)
        score = ScoreDetail(news=1, volume=1, chart=0, candle=0, consolidation=0, supply=0)
        cl = ChecklistDetail(
            is_new_high=False, ma_aligned=False,
            long_candle=False, consolidation_done=False,
        )
        gen._record_candidate(s, score, cl, Grade.C, passed=False)
        reasons = gen.candidates[0]["reasons"]
        assert any("변동성 수축 부족" in r and "BB폭" in r for r in reasons)
        assert any("당일 캔들 약함" in r for r in reasons)
        assert any("차트 약세" in r for r in reasons)

    def test_explicit_exception_reason(self, gen):
        s = _stock("005930", "삼성전자", 70000, 600_000_000_000)
        gen._record_candidate(s, None, None, None, passed=False, reason="분석 오류: TimeoutError")
        assert gen.candidates[0]["reasons"] == ["분석 오류: TimeoutError"]


class TestSaveCandidates:
    def test_save_creates_file(self, gen, tmp_path):
        s = _stock("005930", "삼성전자", 70000, 600_000_000_000)
        score = ScoreDetail(news=2, volume=2, chart=2, candle=1, consolidation=1, supply=0)
        gen._record_candidate(s, score, ChecklistDetail(), Grade.A, passed=True)

        s2 = _stock("000660", "SK하이닉스", 200000, 50_000_000_000)
        score2 = ScoreDetail(news=1, volume=1, chart=0, candle=0, consolidation=0, supply=0)
        gen._record_candidate(s2, score2, ChecklistDetail(), Grade.C, passed=False)

        with patch("engine.generator.DATA_DIR", tmp_path):
            out_path = gen.save_candidates_to_json()

        assert out_path is not None
        payload = json.loads(out_path.read_text(encoding="utf-8"))
        assert payload["passed_count"] == 1
        assert payload["rejected_count"] == 1
        assert payload["passed"][0]["ticker"] == "005930"
        assert payload["rejected"][0]["ticker"] == "000660"
        assert any("낮은 점수" in r for r in payload["rejected"][0]["reasons"])

    def test_save_empty_returns_none(self, gen, tmp_path):
        with patch("engine.generator.DATA_DIR", tmp_path):
            assert gen.save_candidates_to_json() is None
