"""
대화 메모리 관리 (chatbot/memory.py)

세션별로 최근 대화 이력을 관리합니다.
메모리는 인메모리로만 관리되며 서버 재시작 시 초기화됩니다.

설계 의도:
  Gemini API에는 최대 컨텍스트 길이 제한이 있으므로,
  오래된 메시지를 슬라이딩 윈도우 방식으로 제거합니다.
  사용자별로 독립된 memory dict를 관리하여 세션을 격리합니다.
"""

from __future__ import annotations

from collections import deque
from typing import Dict, List


# 세션당 유지할 최대 메시지 수
MAX_MESSAGES_PER_SESSION = 20

# 전역 메모리 저장소: {session_id: deque of {"role": ..., "content": ...}}
_memory_store: Dict[str, deque] = {}


def add_message(session_id: str, role: str, content: str) -> None:
    """
    메시지를 세션 메모리에 추가합니다.

    Args:
        session_id: 사용자 세션 식별자
        role: "user" 또는 "model"
        content: 메시지 내용
    """
    if session_id not in _memory_store:
        _memory_store[session_id] = deque(maxlen=MAX_MESSAGES_PER_SESSION)
    _memory_store[session_id].append({"role": role, "content": content})


def get_history(session_id: str) -> List[dict]:
    """
    세션의 대화 이력을 반환합니다.

    Returns:
        [{"role": "user", "content": "..."}, {"role": "model", ...}, ...]
    """
    return list(_memory_store.get(session_id, []))


def clear_session(session_id: str) -> None:
    """특정 세션의 메모리를 초기화합니다."""
    _memory_store.pop(session_id, None)


def list_sessions() -> List[str]:
    """현재 활성 세션 ID 목록을 반환합니다."""
    return list(_memory_store.keys())
