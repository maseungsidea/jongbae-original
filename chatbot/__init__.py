"""
Chatbot 패키지.
KRStockChatbot 싱글턴 인스턴스를 get_chatbot()으로 제공합니다.
Phase 5에서 KRStockChatbot 구현 후 이 모듈이 완성됩니다.
"""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chatbot.core import KRStockChatbot

_chatbot_instance: "KRStockChatbot | None" = None


def get_chatbot() -> "KRStockChatbot":
    """
    싱글턴 챗봇 인스턴스를 반환합니다.
    최초 호출 시 초기화되며, 이후 호출은 동일 인스턴스를 재사용합니다.
    """
    global _chatbot_instance
    if _chatbot_instance is None:
        from chatbot.core import KRStockChatbot
        _chatbot_instance = KRStockChatbot(user_id="default")
    return _chatbot_instance
