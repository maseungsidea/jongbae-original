"""
12점 채점 시스템 (engine/scorer.py)

종가베팅 시그널의 품질을 6개 항목, 12점 만점으로 평가합니다.

채점 항목:
  1. 뉴스/재료  0~3점 (LLM 기반, 키워드 폴백)
  2. 거래대금   0~3점 (거래대금 규모)
  3. 차트패턴   0~2점 (신고가, 이평선 정배열)
  4. 캔들형태   0~1점 (장대양봉, 윗꼬리 짧음)
  5. 기간조정   0~1점 (횡보 후 돌파, 볼린저 수축)
  6. 수급      0~2점 (외인/기관 순매수)
"""

from __future__ import annotations

import logging
import statistics
from typing import Dict, List, Optional, Tuple

from engine.config import Grade, SignalConfig
from engine.models import (
    ChartData,
    ChecklistDetail,
    NewsItem,
    ScoreDetail,
    StockData,
    SupplyData,
)

logger = logging.getLogger(__name__)


class Scorer:
    """
    12점 만점 종가베팅 채점 시스템.

    각 항목을 독립적으로 채점하여 ScoreDetail을 생성하고,
    ScoreDetail의 총점과 거래대금을 기준으로 등급을 결정합니다.
    """

    def __init__(self, config: SignalConfig):
        self.config = config

    def calculate(
        self,
        stock: StockData,
        charts: List[ChartData],
        news: List[NewsItem],
        supply: Optional[SupplyData],
        llm_result: Optional[Dict],
    ) -> Tuple[ScoreDetail, ChecklistDetail]:
        """
        6개 항목을 채점하여 ScoreDetail과 ChecklistDetail을 반환합니다.

        Args:
            stock: KRX에서 수집한 종목 데이터
            charts: 일봉 데이터 (오름차순 정렬, 최신이 마지막)
            news: 뉴스 기사 목록
            supply: 외인/기관 수급 데이터
            llm_result: LLMAnalyzer.analyze_news_sentiment() 결과 (None이면 키워드 폴백)

        Returns:
            (ScoreDetail, ChecklistDetail) 튜플
        """
        score = ScoreDetail()
        checklist = ChecklistDetail()

        # 1. 뉴스/재료 (0~3점)
        score.news, checklist.has_news, checklist.news_sources = \
            self._score_news(news, llm_result)
        if llm_result and "reason" in llm_result:
            score.llm_reason = llm_result["reason"]

        # 2. 거래대금 (0~3점)
        score.volume = self._score_volume(stock.trading_value)
        checklist.volume_surge = score.volume >= 2

        # 3. 차트패턴 (0~2점)
        score.chart, checklist.is_new_high, checklist.ma_aligned, checklist.is_breakout = \
            self._score_chart(stock, charts)

        # 4. 캔들형태 (0~1점)
        score.candle, checklist.long_candle = self._score_candle(stock, charts)

        # 5. 기간조정 (0~1점)
        score.consolidation, checklist.consolidation_done = self._score_consolidation(charts)

        # 6. 수급 (0~2점)
        score.supply, checklist.supply_positive, checklist.supply_both_positive = \
            self._score_supply(supply)

        return score, checklist

    def determine_grade(self, stock: StockData, score: ScoreDetail) -> Grade:
        """
        총점과 거래대금 기준으로 등급을 결정합니다.

        등급 기준 (engine/config.py GradeConfig 참조):
        - S: 10점+, 거래대금 1조+
        - A: 8점+, 거래대금 5천억+
        - B: 6점+, 거래대금 1천억+
        - C: 기준 미달 (제외 대상)

        Grade B+ 결정 시 Telegram 알림을 발송한다 (utils.notifier 가
        JONGGA_NOTIFY=0 또는 자격증명 부재 시 자동 no-op).
        """
        for grade in [Grade.S, Grade.A, Grade.B]:
            gc = self.config.get_grade_config(grade)
            if score.total >= gc.min_score and stock.trading_value >= gc.min_trading_value:
                self._notify_grade(stock, score, grade)
                return grade
        return Grade.C

    @staticmethod
    def _notify_grade(stock: StockData, score: ScoreDetail, grade: Grade) -> None:
        """채택 시그널을 Telegram 으로 알림. 실패해도 채점 흐름은 영향 받지 않음."""
        try:
            from utils import notifier
            notifier.notify_signal(
                ticker=stock.code,
                name=stock.name,
                grade=grade.value,
                score=score.total,
                entry_price=stock.close,
                stop_price=0,        # PositionSizer 가 결정 — generator 단계에서 알림이 더 정확
                target_price=0,
                market=stock.market,
                trading_value=stock.trading_value,
            )
        except Exception as e:
            logger.debug(f"[scorer] 알림 실패(무시): {e}")

    # ─────────────────────────────────────────
    # 내부 채점 메서드
    # ─────────────────────────────────────────

    def _score_news(
        self, news: List[NewsItem], llm_result: Optional[Dict]
    ) -> Tuple[int, bool, List[str]]:
        """
        뉴스/재료 채점 (0~3점).

        LLM 결과가 있으면 우선 사용하고, 없으면 호재 키워드 매칭으로 폴백합니다.
        LLM 점수: 0=없음, 1=중립, 2=호재, 3=강호재

        Returns:
            (점수, 뉴스 존재 여부, 뉴스 출처 목록)
        """
        has_news = len(news) > 0
        sources = list({n.source for n in news if n.source})

        # LLM 결과 우선 사용
        if llm_result and "score" in llm_result:
            return int(llm_result["score"]), has_news, sources

        # 키워드 기반 폴백
        if not news:
            return 0, False, []

        all_text = " ".join(n.title + " " + n.summary for n in news)
        bullish_hits = sum(1 for kw in self.config.bullish_keywords if kw in all_text)
        bearish_hits = sum(1 for kw in self.config.bearish_keywords if kw in all_text)

        if bearish_hits > 0:
            return max(0, 1 - bearish_hits), has_news, sources

        if bullish_hits >= 3:
            return 3, has_news, sources
        elif bullish_hits >= 2:
            return 2, has_news, sources
        elif bullish_hits >= 1:
            return 1, has_news, sources
        else:
            return 0, has_news, sources

    def _score_volume(self, trading_value: int) -> int:
        """
        거래대금 채점 (0~3점).

        SignalConfig.volume_score_tiers 기준으로 구간 채점합니다.
        """
        for threshold, score in self.config.volume_score_tiers:
            if trading_value >= threshold:
                return score
        return 0

    def _score_chart(
        self, stock: StockData, charts: List[ChartData]
    ) -> Tuple[int, bool, bool, bool]:
        """
        차트패턴 채점 (0~2점).

        - 52주 신고가 여부 (+1점)
        - 이평선 정배열 (MA5 > MA20 > MA60) (+1점)

        Returns:
            (점수, 신고가 여부, 정배열 여부, 돌파 여부)
        """
        score = 0
        is_new_high = False
        ma_aligned = False
        is_breakout = False

        if not charts:
            return score, is_new_high, ma_aligned, is_breakout

        closes = [c.close for c in charts]

        # 52주 신고가: 현재 종가가 52주 최고가에 근접(99%)하거나 초과
        if stock.high_52w:
            is_new_high = stock.close >= stock.high_52w * 0.99
        else:
            # high_52w 없으면 차트 데이터의 최고가와 비교
            lookback = min(len(closes), self.config.new_high_lookback)
            is_new_high = stock.close >= max(closes[-lookback:]) * 0.99

        if is_new_high:
            score += 1

        # 이평선 정배열: MA5 > MA20 > MA60
        ma_days = self.config.ma_alignment_days  # [5, 20, 60]
        if len(closes) >= max(ma_days):
            mas = {d: sum(closes[-d:]) / d for d in ma_days}
            ma_aligned = mas[5] > mas[20] > mas[60]
            if ma_aligned:
                score += 1

        return score, is_new_high, ma_aligned, is_breakout

    def _score_candle(
        self, stock: StockData, charts: List[ChartData]
    ) -> Tuple[int, bool]:
        """
        캔들형태 채점 (0~1점).

        당일 캔들이 장대양봉(몸통 70%+)이고 윗꼬리가 짧으면(10% 이하) +1점.

        Returns:
            (점수, 장대양봉 여부)
        """
        if not charts:
            return 0, False

        today_candle = charts[-1]  # 가장 최근 캔들

        long_body = today_candle.body_ratio >= self.config.long_candle_body_ratio
        short_wick = today_candle.upper_wick_ratio <= self.config.small_upper_wick_ratio
        is_bullish = today_candle.is_bullish

        is_long_candle = long_body and short_wick and is_bullish
        return (1 if is_long_candle else 0), is_long_candle

    def _score_consolidation(self, charts: List[ChartData]) -> Tuple[int, bool]:
        """
        기간조정 채점 (0~1점).

        볼린저 밴드 폭(BB Width)이 임계값 이하로 수축됐다면 횡보 조정으로 판단합니다.
        BB Width = (Upper - Lower) / Middle
        임계값: SignalConfig.consolidation_bb_squeeze_pct (기본 3%)

        Returns:
            (점수, 횡보 완료 여부)
        """
        if len(charts) < 20:
            return 0, False

        closes = [c.close for c in charts[-20:]]
        mean = sum(closes) / len(closes)

        # 표준편차 기반 볼린저 밴드
        std = statistics.stdev(closes)
        upper = mean + 2 * std
        lower = mean - 2 * std
        bb_width = (upper - lower) / mean if mean > 0 else 0

        is_squeezed = bb_width <= self.config.consolidation_bb_squeeze_pct
        return (1 if is_squeezed else 0), is_squeezed

    def _score_supply(
        self, supply: Optional[SupplyData]
    ) -> Tuple[int, bool, bool]:
        """
        수급 채점 (0~2점).

        - 외인 또는 기관 중 하나 순매수 → +1점
        - 외인 + 기관 모두 순매수 → +2점 (추가 +1)

        SignalConfig.supply_enabled=False 면 항상 0 (KRX 수급 API 차단 시
        라이브-백테 정합성 위해 강제 무력화).

        Returns:
            (점수, 수급 긍정 여부, 외인+기관 동시 순매수 여부)
        """
        if not getattr(self.config, "supply_enabled", True):
            return 0, False, False

        if supply is None:
            return 0, False, False

        either = supply.is_either_positive
        both = supply.is_both_positive

        if both:
            return 2, True, True
        elif either:
            return 1, True, False
        else:
            return 0, False, False
