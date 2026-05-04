"""
포지션 사이징 및 리스크 관리 (engine/position_sizer.py)

1R(리스크 단위) 기반 켈리 기준 변형 방식으로 진입가, 손절가, 목표가,
포지션 금액, 수량을 계산합니다.

설계 의도:
  - 계좌 자산의 고정 비율(r_ratio, 기본 0.5%)을 1R로 정의
  - 등급에 따라 R 배수가 다르므로, 고확신 종목에 자동으로 더 많이 배분
  - 단일 포지션 최대 비율(max_position_pct)로 과도한 집중을 방지
"""

from __future__ import annotations

from dataclasses import dataclass
from math import floor

from engine.config import Grade, SignalConfig


@dataclass
class PositionResult:
    """포지션 사이징 계산 결과"""
    entry_price: float      # 진입가 (현재가)
    stop_price: float       # 손절가 (entry × (1 - stop_loss_pct))
    target_price: float     # 목표가 (entry × (1 + take_profit_pct))
    r_value: float          # 1R 금액 (계좌 × r_ratio)
    position_size: float    # 투자 금액 (원)
    quantity: int           # 매수 수량 (주)
    r_multiplier: float     # 등급별 R 배수


class PositionSizer:
    """
    자금 관리 및 포지션 사이징.

    계산 흐름:
    1. entry_price = current_price
    2. stop_price  = entry × (1 - stop_loss_pct)
    3. target_price = entry × (1 + take_profit_pct)
    4. r_value      = capital × r_ratio              ← 1R 손실 허용액
    5. risk_per_share = entry - stop_price           ← 주당 손실
    6. raw_size     = r_value × r_multiplier / risk_per_share
    7. position_size = min(raw_size, capital × max_position_pct)
    8. quantity     = floor(position_size / entry_price)
    """

    def __init__(self, capital: float, config: SignalConfig):
        """
        Args:
            capital: 투자 가능 총 자산 (원)
            config: 손절/익절/리스크 비율이 담긴 SignalConfig
        """
        self.capital = capital
        self.config = config

    def calculate(self, price: float, grade: Grade) -> PositionResult:
        """
        현재가와 등급을 받아 포지션 사이징 결과를 반환합니다.

        Args:
            price: 현재가 (종가 기준)
            grade: 시그널 등급 (S/A/B)

        Returns:
            PositionResult 인스턴스

        Raises:
            ValueError: price가 0 이하인 경우
        """
        if price <= 0:
            raise ValueError(f"종가가 0 이하입니다: {price}")

        # 등급별 R 배수 조회
        grade_cfg = self.config.get_grade_config(grade)
        r_multiplier = grade_cfg.r_multiplier

        # 가격 계산
        entry_price = price
        stop_price = entry_price * (1 - self.config.stop_loss_pct / 100)
        target_price = entry_price * (1 + self.config.take_profit_pct / 100)

        # 리스크 계산
        r_value = self.capital * self.config.r_ratio
        risk_per_share = entry_price - stop_price

        if risk_per_share <= 0:
            # 손절가가 진입가 이상인 비정상 상황 (절대 발생하지 않아야 하나 방어 코드)
            risk_per_share = entry_price * 0.01

        # 포지션 금액 계산 (최대 자산 비율 제한 적용)
        raw_size = r_value * r_multiplier / risk_per_share
        max_size = self.capital * self.config.max_position_pct if hasattr(self.config, "max_position_pct") else self.capital * 0.2
        position_size = min(raw_size, max_size)

        # 매수 수량 (소수점 이하 버림: 부족 자금 방지)
        quantity = floor(position_size / entry_price)

        # 수량이 0이면 최소 1주라도 매수 (소액 계좌 대응)
        if quantity < 1:
            quantity = 1
            position_size = entry_price

        return PositionResult(
            entry_price=round(entry_price, 0),
            stop_price=round(stop_price, 0),
            target_price=round(target_price, 0),
            r_value=round(r_value, 0),
            position_size=round(position_size, 0),
            quantity=quantity,
            r_multiplier=r_multiplier,
        )
