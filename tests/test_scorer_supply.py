"""scorer.py 의 supply_enabled 옵션 동작 확인."""

from __future__ import annotations

from engine.config import SignalConfig
from engine.models import SupplyData
from engine.scorer import Scorer


def _supply_pos() -> SupplyData:
    # 외인/기관 모두 순매수 → 정상 동작 시 +2점
    return SupplyData(foreign_buy_5d=10000, inst_buy_5d=20000)


class TestSupplyEnabled:
    def test_supply_disabled_forces_zero(self):
        cfg = SignalConfig()
        cfg.supply_enabled = False
        scorer = Scorer(cfg)
        score, _, _ = scorer._score_supply(_supply_pos())
        assert score == 0

    def test_supply_enabled_returns_full_score(self):
        cfg = SignalConfig()
        cfg.supply_enabled = True
        scorer = Scorer(cfg)
        score, either, both = scorer._score_supply(_supply_pos())
        assert score == 2
        assert either is True
        assert both is True

    def test_default_config_disables_supply(self):
        # 운영 default 가 False — KRX API 차단 동안 라이브와 백테 정합성 보장
        cfg = SignalConfig()
        assert cfg.supply_enabled is False
