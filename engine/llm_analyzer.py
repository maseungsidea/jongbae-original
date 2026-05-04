"""
Gemini LLM 뉴스 감성 분석 모듈 (engine/llm_analyzer.py)

Google Gemini API를 사용하여 종목 뉴스의 호재/악재 감성을 분석하고
0~3점 점수와 분석 요약을 반환합니다.

API 키가 없거나 오류 발생 시 None을 반환하며,
Scorer는 None을 받으면 키워드 기반 폴백으로 전환합니다.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class LLMAnalyzer:
    """
    Gemini LLM 기반 뉴스 감성 분석기.

    LLM 호출 비용과 속도 균형을 위해:
    - 뉴스 제목만 전달 (요약 없음)
    - 최대 llm_news_limit 개 뉴스만 처리
    - JSON 응답 강제 (Structured Output)
    - 타임아웃 = SignalConfig.llm_timeout_sec (기본 10초)
    """

    PROMPT_TEMPLATE = """
당신은 주식 투자 전문가입니다.
아래는 {stock_name} 종목의 최근 뉴스 제목 목록입니다.

뉴스:
{news_text}

이 뉴스들이 종가베팅(당일 종가 진입 → 익일 매도) 전략에서
주가에 미치는 단기 영향을 분석하세요.

반드시 아래 JSON 형식으로만 답하세요. JSON 외 텍스트는 허용하지 않습니다.
{{
  "score": <0~3 정수. 0=영향없음/악재, 1=중립, 2=호재, 3=강호재>,
  "sentiment": "<positive|neutral|negative>",
  "reason": "<50자 이내 한국어 핵심 근거>"
}}
"""

    def __init__(self, api_key: Optional[str] = None):
        """
        Args:
            api_key: Gemini API 키. None이면 환경변수 GEMINI_API_KEY 사용.
        """
        self._api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.model = None

        if self._api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self._api_key)
                self.model = genai.GenerativeModel("gemini-1.5-flash")
                logger.info("[LLMAnalyzer] Gemini 모델 초기화 성공")
            except Exception as e:
                logger.warning(f"[LLMAnalyzer] Gemini 초기화 실패: {e}")
        else:
            logger.info("[LLMAnalyzer] API 키 없음 → 키워드 폴백 모드")

    async def analyze_news_sentiment(
        self, stock_name: str, news_items: List[Dict]
    ) -> Optional[Dict]:
        """
        뉴스 목록에 대한 감성 분석을 수행합니다.

        Args:
            stock_name: 종목명 (프롬프트에 포함)
            news_items: [{"title": ..., "source": ...}, ...] 형태의 뉴스 목록

        Returns:
            {"score": int, "sentiment": str, "reason": str} 또는 None (실패 시)
        """
        if self.model is None or not news_items:
            return None

        # 뉴스 제목만 추출, 개수 제한
        from engine.config import SignalConfig
        limit = SignalConfig().llm_news_limit
        titles = [item.get("title", "") for item in news_items[:limit] if item.get("title")]

        if not titles:
            return None

        news_text = "\n".join(f"- {t}" for t in titles)
        prompt = self.PROMPT_TEMPLATE.format(
            stock_name=stock_name,
            news_text=news_text,
        )

        try:
            # Gemini는 동기 API이므로 asyncio.to_thread 로 실행
            from engine.config import SignalConfig
            timeout = SignalConfig().llm_timeout_sec

            response = await asyncio.wait_for(
                asyncio.to_thread(self.model.generate_content, prompt),
                timeout=timeout,
            )

            raw_text = response.text.strip()

            # JSON 파싱 (마크다운 코드블록 제거)
            if raw_text.startswith("```"):
                raw_text = raw_text.split("```")[1]
                if raw_text.startswith("json"):
                    raw_text = raw_text[4:]

            result = json.loads(raw_text.strip())

            # 스키마 검증
            score = int(result.get("score", 0))
            score = max(0, min(3, score))  # 0~3 범위 강제

            return {
                "score": score,
                "sentiment": result.get("sentiment", "neutral"),
                "reason": result.get("reason", "")[:100],  # 최대 100자
            }

        except asyncio.TimeoutError:
            logger.warning(f"[LLMAnalyzer] {stock_name} 타임아웃")
            return None
        except json.JSONDecodeError as e:
            logger.warning(f"[LLMAnalyzer] JSON 파싱 오류 ({stock_name}): {e}")
            return None
        except Exception as e:
            logger.error(f"[LLMAnalyzer] {stock_name} 분석 오류: {e}")
            return None
