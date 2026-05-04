"""
대화 이력 영구 저장 (chatbot/history.py)

대화 이력을 JSON 파일로 저장하여 서버 재시작 후에도 복원할 수 있게 합니다.
각 세션은 별도 파일로 관리됩니다.

설계 의도:
  인메모리 memory.py는 속도가 빠르지만 재시작 시 초기화됩니다.
  history.py는 중요 대화를 파일로 백업하여 장기 기억을 제공합니다.
  두 모듈을 분리하여 메모리와 영구 저장의 책임을 명확히 구분합니다.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
HISTORY_DIR = ROOT / "data" / "chat_history"


def _session_path(session_id: str) -> Path:
    """세션 파일 경로를 반환합니다."""
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    # session_id에 특수문자가 있을 경우 안전하게 파일명으로 변환
    safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in session_id)
    return HISTORY_DIR / f"{safe_id}.json"


def save_message(session_id: str, role: str, content: str) -> None:
    """
    메시지를 세션의 JSON 파일에 저장합니다.

    Args:
        session_id: 사용자 세션 식별자
        role: "user" 또는 "model"
        content: 메시지 내용
    """
    try:
        path = _session_path(session_id)
        history = load_history(session_id)
        history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
        })
        with open(path, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"[history] 저장 실패 ({session_id}): {e}")


def load_history(session_id: str, limit: Optional[int] = None) -> List[dict]:
    """
    세션의 대화 이력을 파일에서 로드합니다.

    Args:
        session_id: 사용자 세션 식별자
        limit: 최근 N개만 반환 (None이면 전체)

    Returns:
        [{"role": ..., "content": ..., "timestamp": ...}, ...]
    """
    path = _session_path(session_id)
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if limit:
            return data[-limit:]
        return data
    except Exception as e:
        logger.warning(f"[history] 로드 실패 ({session_id}): {e}")
        return []


def clear_history(session_id: str) -> None:
    """세션 이력 파일을 삭제합니다."""
    path = _session_path(session_id)
    if path.exists():
        path.unlink()
