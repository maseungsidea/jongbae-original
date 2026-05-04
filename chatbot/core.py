"""
챗봇 코어 (chatbot/core.py)

Gemini LLM을 활용한 KRStockChatbot 구현.
시장 데이터 컨텍스트를 주입하여 맥락 있는 투자 조언을 제공합니다.

설계 의도:
  google-generativeai의 ChatSession은 자체 history를 관리하지만,
  서버 재시작 시 초기화되기 때문에 chatbot/history.py와 chatbot/memory.py를
  함께 사용합니다. ChatSession에는 최근 N개 대화만 제공하여 토큰을 절약합니다.
"""

from __future__ import annotations

import logging
import os
from typing import List, Optional

logger = logging.getLogger(__name__)


class KRStockChatbot:
    """
    Gemini 기반 한국 주식 종가배팅 전문 챗봇.

    싱글턴 패턴 사용: chatbot/__init__.py의 get_chatbot()을 통해 접근.
    """

    def __init__(self, user_id: str = "default"):
        self.user_id = user_id
        self._model = None
        self._api_key: Optional[str] = None
        self._initialized = False

    def _ensure_init(self) -> None:
        """Gemini 클라이언트를 지연 초기화합니다."""
        if self._initialized:
            return

        self._api_key = os.environ.get("GEMINI_API_KEY", "")
        if not self._api_key:
            logger.warning("[chatbot] GEMINI_API_KEY 미설정. 챗봇 기능 제한됨.")
            self._initialized = True
            return

        try:
            import google.generativeai as genai
            genai.configure(api_key=self._api_key)
            self._model = genai.GenerativeModel(
                model_name="gemini-1.5-flash",
                generation_config={
                    "temperature": 0.7,
                    "max_output_tokens": 1024,
                },
            )
            logger.info("[chatbot] Gemini 초기화 완료")
        except ImportError:
            logger.error("[chatbot] google-generativeai 패키지 없음. pip install google-generativeai")
        except Exception as e:
            logger.error(f"[chatbot] Gemini 초기화 오류: {e}")

        self._initialized = True

    def chat(self, message: str, session_id: str = "default") -> str:
        """
        사용자 메시지에 응답합니다.

        Args:
            message: 사용자 입력 텍스트
            session_id: 대화 세션 식별자

        Returns:
            AI 응답 텍스트
        """
        self._ensure_init()

        # API 키 없으면 안내 메시지
        if not self._api_key:
            return (
                "⚠️ GEMINI_API_KEY가 설정되지 않아 AI 챗봇을 사용할 수 없습니다.\n"
                ".env 파일에 GEMINI_API_KEY를 설정해주세요."
            )

        if self._model is None:
            return "챗봇 초기화에 실패했습니다. 서버 로그를 확인해주세요."

        try:
            # 메모리에서 대화 이력 가져오기 및 현재 메시지 저장
            from chatbot.memory import add_message, get_history
            from chatbot.history import save_message
            from chatbot.data_loader import get_market_context, get_stock_context
            from chatbot.prompts import build_system_prompt, detect_intent

            # 의도 감지 → 추가 컨텍스트 주입
            intent = detect_intent(message)
            market_ctx = get_market_context()

            # 종목 코드 패턴 감지 (6자리 숫자)
            import re
            ticker_matches = re.findall(r"\b(\d{6})\b", message)
            if ticker_matches:
                stock_ctxs = [get_stock_context(t) for t in ticker_matches[:2]]
                market_ctx += "\n" + "\n".join(filter(None, stock_ctxs))

            system_prompt = build_system_prompt(market_ctx)

            # LLM 대화 기록 조립 (Gemini 형식)
            history = get_history(session_id)
            gemini_history: List[dict] = [
                {"role": "user" if m["role"] == "user" else "model", "parts": [m["content"]]}
                for m in history
            ]

            # 새 채팅 세션 생성 (history 포함)
            chat_session = self._model.start_chat(history=gemini_history)

            # 시스템 프롬프트를 첫 메시지에 함께 전달
            full_message = f"{system_prompt}\n\n사용자: {message}" if not history else message
            response = chat_session.send_message(full_message)
            reply = response.text

            # 메모리 + 파일 저장
            add_message(session_id, "user", message)
            add_message(session_id, "model", reply)
            save_message(session_id, "user", message)
            save_message(session_id, "model", reply)

            return reply

        except Exception as e:
            logger.error(f"[chatbot] chat 오류 (session={session_id}): {e}")
            return f"오류가 발생했습니다: {str(e)}"

    def reset_session(self, session_id: str = "default") -> None:
        """특정 세션의 대화 이력을 초기화합니다."""
        from chatbot.memory import clear_session
        from chatbot.history import clear_history
        clear_session(session_id)
        clear_history(session_id)
        logger.info(f"[chatbot] 세션 초기화: {session_id}")
