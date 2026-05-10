"""
시그널 생성 오케스트레이터 (engine/generator.py)

SignalGenerator가 KRXCollector, EnhancedNewsCollector, LLMAnalyzer,
Scorer, PositionSizer를 조합하여 종가베팅 시그널을 생성합니다.

주요 진입점:
- run_screener()         : 전체 마켓 스크리닝 (Flask API에서 호출)
- analyze_single_stock_by_code(): 단일 종목 분석 (AI 요약 API에서 호출)
- save_result_to_json()  : 결과를 data/ 폴더에 JSON으로 저장
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional

from engine.collectors import EnhancedNewsCollector, KRXCollector
from engine.config import Grade, SignalConfig
from engine.llm_analyzer import LLMAnalyzer
from engine.models import (
    ChartData,
    NewsItem,
    ScreenerResult,
    Signal,
    SignalStatus,
    StockData,
    SupplyData,
)
from engine.position_sizer import PositionSizer
from engine.scorer import Scorer

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"


class SignalGenerator:
    """
    종가베팅 시그널 생성 오케스트레이터.

    처리 흐름:
    1. KRXCollector로 KOSPI/KOSDAQ 당일 상승 상위 종목 수집
    2. 각 종목에 대해 차트(90일), 뉴스, 수급 병렬 수집
    3. LLMAnalyzer로 뉴스 감성 분석 (API 키 없으면 스킵)
    4. Scorer로 12점 채점 후 Grade C(미달) 필터링
    5. PositionSizer로 진입가/손절가/목표가/수량 계산
    6. Signal 객체 생성 및 반환

    async with SignalGenerator(...) as gen: 형태로 사용합니다.
    """

    def __init__(
        self,
        config: Optional[SignalConfig] = None,
        capital: float = 10_000_000,
    ):
        self.config = config or SignalConfig()
        self.capital = capital
        self._krx: Optional[KRXCollector] = None
        self._news: Optional[EnhancedNewsCollector] = None
        self._llm = LLMAnalyzer()
        self._scorer = Scorer(self.config)
        self._sizer = PositionSizer(self.capital, self.config)
        self.candidates: List[Dict] = []

    async def __aenter__(self) -> "SignalGenerator":
        self._krx = KRXCollector(self.config)
        self._news = EnhancedNewsCollector(self.config)
        await self._krx.__aenter__()
        await self._news.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._krx:
            await self._krx.__aexit__(exc_type, exc_val, exc_tb)
        if self._news:
            await self._news.__aexit__(exc_type, exc_val, exc_tb)

    async def generate(
        self,
        target_date: Optional[date] = None,
        markets: Optional[List[str]] = None,
        top_n: int = 30,
    ) -> List[Signal]:
        """
        전체 마켓 스크리닝을 실행하여 시그널 목록을 반환합니다.

        모든 후보의 채점 결과를 ``self.candidates`` 에 누적 (passed + rejected).
        이후 save_candidates_to_json() 으로 별도 파일에 저장 가능.

        Args:
            target_date: 분석 기준일 (None이면 오늘)
            markets: 분석할 시장 목록 (기본: ["KOSPI", "KOSDAQ"])
            top_n: 시장별 상위 종목 수 (기본: 30)

        Returns:
            Grade B 이상 시그널 목록 (등급·점수 내림차순)
        """
        if markets is None:
            markets = ["KOSPI", "KOSDAQ"]

        # 이번 실행의 후보 누적 컨테이너 — passed + rejected 모두 기록
        self.candidates: List[Dict] = []

        t_start = time.perf_counter()
        all_stocks: List[StockData] = []

        # 시장별 상위 종목 수집
        for market in markets:
            stocks = await self._krx.get_top_gainers(market, top_n)
            all_stocks.extend(stocks)
            logger.info(f"[Generator] {market} {len(stocks)}개 종목 수집")

        logger.info(f"[Generator] 총 {len(all_stocks)}개 분석 시작")

        # 종목별 분석 (최대 10개 동시 실행으로 KRX 부하 제어)
        semaphore = asyncio.Semaphore(10)
        tasks = [self._analyze_stock(stock, target_date, semaphore) for stock in all_stocks]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        signals: List[Signal] = []
        for r in results:
            if isinstance(r, Signal):
                signals.append(r)
            elif isinstance(r, Exception):
                logger.debug(f"[Generator] 분석 중 예외: {r}")

        # 등급 → 점수 내림차순 정렬
        grade_order = {Grade.S: 0, Grade.A: 1, Grade.B: 2, Grade.C: 3}
        signals.sort(key=lambda s: (grade_order.get(s.grade, 9), -s.score.total))

        elapsed = (time.perf_counter() - t_start) * 1000
        passed_n = sum(1 for c in self.candidates if c.get("passed"))
        logger.info(
            f"[Generator] 완료: {len(signals)}개 시그널 / {len(self.candidates)} "
            f"후보 평가 (통과 {passed_n}) ({elapsed:.0f}ms)"
        )
        return signals

    async def _analyze_stock(
        self,
        stock: StockData,
        target_date: Optional[date],
        semaphore: asyncio.Semaphore,
    ) -> Optional[Signal]:
        """
        단일 종목 전체 분석 파이프라인.

        1. 차트·뉴스·수급 병렬 수집
        2. LLM 뉴스 분석
        3. 12점 채점 + 등급 결정
        4. Grade C이면 None 반환 (사유와 함께 self.candidates 에 기록)
        5. PositionSizer로 포지션 계산
        6. Signal 객체 생성
        """
        async with semaphore:
            try:
                # 1. 데이터 병렬 수집
                charts, news, supply = await asyncio.gather(
                    self._krx.get_chart_data(stock.code, days=90),
                    self._news.get_stock_news(
                        stock.code, limit=self.config.llm_news_limit, name=stock.name
                    ),
                    self._krx.get_supply_data(stock.code),
                )

                # 2. LLM 뉴스 분석
                news_dicts = [
                    {"title": n.title, "source": n.source, "url": n.url}
                    for n in news
                ]
                llm_result = await self._llm.analyze_news_sentiment(stock.name, news_dicts)

                # 3. 채점 + 등급
                score, checklist = self._scorer.calculate(
                    stock, charts, news, supply, llm_result
                )
                grade = self._scorer.determine_grade(stock, score)

                # 4. 미달 필터 → 거부 사유 기록 후 종료
                if grade == Grade.C:
                    self._record_candidate(
                        stock, score, checklist, grade, passed=False,
                    )
                    return None

                # 5. 포지션 계산 (ATR 가용 시 ATR 기반 stop)
                atr_today: float | None = None
                try:
                    if charts and len(charts) >= 15:
                        from engine.trailing_stop import compute_atr
                        period = getattr(self.config, "atr_period", 14)
                        atr_series = compute_atr(
                            [c.high for c in charts],
                            [c.low for c in charts],
                            [c.close for c in charts],
                            period=period,
                        )
                        if atr_series:
                            atr_today = atr_series[-1]
                except Exception as _e:
                    logger.debug(f"ATR 계산 실패 ({stock.code}): {_e}")
                pos = self._sizer.calculate(stock.close, grade, atr_value=atr_today)

                # 6. Signal 생성 + 후보 기록 (통과)
                now = datetime.now()
                signal = Signal(
                    stock_code=stock.code,
                    stock_name=stock.name,
                    market=stock.market,
                    sector=stock.sector,
                    signal_date=target_date or date.today(),
                    signal_time=now,
                    grade=grade,
                    score=score,
                    checklist=checklist,
                    news_items=news_dicts,
                    current_price=stock.close,
                    entry_price=pos.entry_price,
                    stop_price=pos.stop_price,
                    target_price=pos.target_price,
                    r_value=pos.r_value,
                    position_size=pos.position_size,
                    quantity=pos.quantity,
                    r_multiplier=pos.r_multiplier,
                    trading_value=stock.trading_value,
                    change_pct=stock.change_pct,
                    status=SignalStatus.PENDING,
                    created_at=now,
                )
                
                # 통과 후보 기록
                self._record_candidate(stock, score, checklist, grade, passed=True)
                
                return signal

            except Exception as e:
                # 예외 케이스: 후보 기록 후 None 반환
                self._record_candidate(
                    stock, None, None, None, passed=False, 
                    reason=f"분석 오류: {str(e)[:50]}"
                )
                logger.warning(f"[Generator] {stock.code}({stock.name}) 분석 오류: {e}")
                return None

    def _record_candidate(
        self,
        stock: StockData,
        score=None,
        checklist=None,
        grade: Optional[Grade] = None,
        passed: bool = False,
        reason: str = "",
    ) -> None:
        """
        후보 종목을 self.candidates에 기록합니다.

        passed=True  → 통과 종목 (reasons 비어있음)
        passed=False → 거부 사유 카테고리 산출 후 reasons 에 누적
        reason       → 외부에서 명시 사유 (예외 케이스) 직접 주입
        """
        if not hasattr(self, "candidates") or self.candidates is None:
            self.candidates = []

        total = (
            score.total if score is not None and hasattr(score, "total")
            else (score.get("total", 0) if isinstance(score, dict) else 0)
        )
        grade_val = (
            grade.value if grade is not None and hasattr(grade, "value")
            else (str(grade) if grade is not None else "?")
        )

        reasons: List[str] = []
        if reason:
            reasons.append(reason)
        if not passed and score is not None:
            reasons.extend(self._build_reject_reasons(stock, score, checklist))

        candidate: Dict = {
            "ticker": stock.code,
            "name": stock.name,
            "market": stock.market,
            "passed": passed,
            "score": total,
            "grade": grade_val,
            "current_price": int(round(stock.close)),
            "change_pct": round(stock.change_pct, 2),
            "trading_value": stock.trading_value,
            "reasons": reasons,
        }
        if score is not None and hasattr(score, "to_dict"):
            candidate["score_breakdown"] = score.to_dict()

        self.candidates.append(candidate)

    def _build_reject_reasons(
        self, stock: StockData, score, checklist
    ) -> List[str]:
        """Grade C 떨어진 후보의 카테고리별 한글 사유 생성."""
        reasons: List[str] = []
        gc_b = self.config.get_grade_config(Grade.B)

        score_total = getattr(score, "total", 0)
        # 1) 점수 미달
        if score_total < gc_b.min_score:
            reasons.append(f"낮은 점수({score_total}점, B등급 {gc_b.min_score}점 필요)")
        # 2) 거래대금 미달
        if stock.trading_value < gc_b.min_trading_value:
            reasons.append(
                f"거래대금 미달({stock.trading_value/1e8:,.0f}억, "
                f"B등급 {gc_b.min_trading_value/1e8:,.0f}억 필요)"
            )
        # 3) 양쪽 다 통과인데 C 면 약한 등급으로만 명시
        if not reasons:
            reasons.append(f"약한 Grade(C등급, 총점 {score_total}점)")

        # 보조 사유 (체크리스트)
        if checklist is not None:
            if not getattr(checklist, "consolidation_done", False):
                # 실제 조건: 20일 BB폭 = (upper-lower)/mean ≤ consolidation_bb_squeeze_pct
                # 'VCP 미성숙' 은 오해 소지 — 단일 BB폭 임계 검사일 뿐.
                threshold_pct = self.config.consolidation_bb_squeeze_pct * 100
                reasons.append(
                    f"변동성 수축 부족 (20일 BB폭 > {threshold_pct:.0f}%)"
                )
            if not getattr(checklist, "long_candle", False):
                reasons.append("당일 캔들 약함(장대양봉 아님)")
            if not (
                getattr(checklist, "is_new_high", False)
                or getattr(checklist, "ma_aligned", False)
            ):
                reasons.append("차트 약세(신고가·정배열 둘 다 미충족)")

        return reasons

    def save_candidates_to_json(self) -> Optional[Path]:
        """
        self.candidates를 data/jongga_v2_candidates.json으로 저장합니다.
        
        통과 종목과 탈락 종목을 분리하여 저장합니다:
        {
            "date": "2026-05-08",
            "passed_count": N,
            "rejected_count": M,
            "passed": [...],
            "rejected": [...]
        }
        """
        if not self.candidates:
            logger.info("[Generator] 후보 종목 없음 (저장 스킵)")
            return None
        
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        out_path = DATA_DIR / "jongga_v2_candidates.json"
        
        passed = [c for c in self.candidates if c.get("passed")]
        rejected = [c for c in self.candidates if not c.get("passed")]
        
        payload = {
            "date": date.today().isoformat(),
            "total_evaluated": len(self.candidates),
            "passed_count": len(passed),
            "rejected_count": len(rejected),
            "passed": passed,
            "rejected": rejected,
        }
        
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        
        logger.info(
            f"[Generator] 후보 분석 결과 저장: {out_path} "
            f"(통과 {len(passed)} / 탈락 {len(rejected)})"
        )
        return out_path

    def get_summary(self, signals: List[Signal]) -> Dict:
        """시그널 목록의 요약 통계를 반환합니다."""
        by_grade: Dict[str, int] = {}
        by_market: Dict[str, int] = {}

        for s in signals:
            grade_key = s.grade.value if hasattr(s.grade, "value") else str(s.grade)
            by_grade[grade_key] = by_grade.get(grade_key, 0) + 1
            by_market[s.market] = by_market.get(s.market, 0) + 1

        return {
            "total": len(signals),
            "by_grade": by_grade,
            "by_market": by_market,
        }


# ─────────────────────────────────────────
# 편의 함수 (Flask API에서 직접 호출)
# ─────────────────────────────────────────

async def run_screener(
    capital: float = 50_000_000,
    config: Optional[SignalConfig] = None,
    markets: Optional[List[str]] = None,
    top_n: int = 30,
) -> ScreenerResult:
    """
    전체 스크리너 실행 후 ScreenerResult를 반환합니다.

    Flask API 엔드포인트(/api/kr/vcp-scan)에서 asyncio.run()으로 호출합니다.

    Args:
        capital: 투자 가능 자산
        config: SignalConfig (None이면 기본값)
        markets: 분석 시장 (None이면 KOSPI+KOSDAQ)
        top_n: 시장별 상위 종목 수

    Returns:
        ScreenerResult
    """
    cfg = config or SignalConfig()
    t_start = time.perf_counter()

    async with SignalGenerator(config=cfg, capital=capital) as gen:
        signals = await gen.generate(markets=markets, top_n=top_n)
        summary = gen.get_summary(signals)
        
        # 후보 분석 결과 저장
        gen.save_candidates_to_json()

    elapsed = (time.perf_counter() - t_start) * 1000
    return ScreenerResult(
        date=date.today(),
        total_candidates=top_n * len(markets or ["KOSPI", "KOSDAQ"]),
        filtered_count=len(signals),
        signals=signals,
        by_grade=summary["by_grade"],
        by_market=summary["by_market"],
        processing_time_ms=elapsed,
    )


async def analyze_single_stock_by_code(
    code: str,
    capital: float = 50_000_000,
    config: Optional[SignalConfig] = None,
) -> Optional[Signal]:
    """
    단일 종목 코드로 분석을 실행합니다.

    Flask API 엔드포인트(/api/kr/ai-summary/<ticker>)에서 호출합니다.

    Args:
        code: 6자리 종목코드
        capital: 투자 자산
        config: SignalConfig

    Returns:
        Signal 또는 None (Grade C / 오류)
    """
    cfg = config or SignalConfig()
    semaphore = asyncio.Semaphore(1)

    async with SignalGenerator(config=cfg, capital=capital) as gen:
        stock = await gen._krx.get_stock_detail(code)
        if stock is None:
            logger.warning(f"[analyze_single] {code} 종목 데이터 없음")
            return None
        return await gen._analyze_stock(stock, None, semaphore)


def save_result_to_json(result: ScreenerResult) -> Path:
    """
    ScreenerResult를 data/jongga_v2_latest.json 으로 저장합니다.
    이전 파일을 덮어씁니다.

    Returns:
        저장된 파일 경로
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DATA_DIR / "jongga_v2_latest.json"

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)

    logger.info(f"[Generator] 결과 저장: {out_path}")

    # 추천종목 요약본 (텔레그램 일일 알림용 슬림 포맷)
    save_today_recommendations(result)
    return out_path


def save_today_recommendations(result: ScreenerResult) -> Path:
    """오늘 추천종목 슬림 요약본 저장 (텔레그램 알림 소비용).

    필드: ticker, name, grade, score, price, market, trading_value
    grade 순(S>A>B), 동등시 score 내림차순 정렬.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DATA_DIR / "today_recommendations.json"

    grade_rank = {"S": 0, "A": 1, "B": 2, "C": 3}
    items = []
    for s in result.signals:
        grade_val = s.grade.value if hasattr(s.grade, "value") else str(s.grade)
        items.append({
            "ticker": s.stock_code,
            "name": s.stock_name,
            "grade": grade_val,
            "score": s.score.total,
            "price": int(round(s.current_price)),
            "market": s.market,
            "trading_value": s.trading_value,
        })
    items.sort(key=lambda x: (grade_rank.get(x["grade"], 9), -x["score"]))

    payload = {
        "date": result.date.isoformat() if hasattr(result, "date") else None,
        "count": len(items),
        "items": items,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    logger.info(f"[Generator] 추천종목 요약 저장: {out_path} ({len(items)}개)")
    return out_path
