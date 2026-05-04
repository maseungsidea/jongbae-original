"""
섹터 캐시 유틸 (app/utils/cache.py)

용도:
- SECTOR_MAP: 주요 종목코드 → 섹터명 정적 매핑
- get_sector(): 종목코드 → 섹터 반환 (SECTOR_MAP 우선, 없으면 빈 문자열)
- TTLCache: 엔드포인트 결과 캐싱 (만료 시간 기반)
"""

from __future__ import annotations

import time
import threading
from typing import Any, Dict, Optional


# ─────────────────────────────────────────
# 섹터 정적 매핑
# (KRX 섹터 API 호출 없이 빠르게 조회하기 위한 캐시)
# ─────────────────────────────────────────

SECTOR_MAP: Dict[str, str] = {
    # 반도체
    "005930": "반도체",   # 삼성전자
    "000660": "반도체",   # SK하이닉스
    "042700": "반도체",   # 한미반도체
    "039130": "반도체",   # 하나마이크론
    # 2차전지
    "373220": "2차전지",  # LG에너지솔루션
    "006400": "2차전지",  # 삼성SDI
    "051910": "2차전지",  # LG화학
    "096770": "2차전지",  # SK이노베이션
    "247540": "2차전지",  # 에코프로비엠
    "086520": "2차전지",  # 에코프로
    # 자동차
    "005380": "자동차",   # 현대자동차
    "000270": "자동차",   # 기아
    "012330": "자동차",   # 현대모비스
    # IT/소프트웨어
    "035420": "IT",       # NAVER
    "035720": "IT",       # 카카오
    "259960": "IT",       # 크래프톤
    # 바이오/헬스케어
    "068270": "바이오",   # 셀트리온
    "207940": "바이오",   # 삼성바이오로직스
    "326030": "바이오",   # SK바이오팜
    # 은행/금융
    "105560": "금융",     # KB금융
    "055550": "금융",     # 신한지주
    "086790": "금융",     # 하나금융지주
    # 철강/소재
    "005490": "철강",     # POSCO홀딩스
    "004020": "철강",     # 현대제철
    # 에너지
    "096610": "에너지",   # 에스오일
    "010950": "에너지",   # S-Oil
    # 인터넷/플랫폼
    "293490": "게임",     # 카카오게임즈
    "251270": "게임",     # 넷마블
    # 방산
    "012450": "방산",     # 한화에어로스페이스
    "047810": "방산",     # 한국항공우주
}


def get_sector(ticker: str) -> str:
    """
    종목코드에 해당하는 섹터를 반환합니다.
    SECTOR_MAP에 없으면 빈 문자열을 반환합니다.

    Args:
        ticker: 6자리 종목코드 (앞 0 포함)

    Returns:
        섹터명 ("반도체", "2차전지", ...) 또는 ""
    """
    return SECTOR_MAP.get(str(ticker).zfill(6), "")


# ─────────────────────────────────────────
# TTL 캐시 (만료 시간 기반)
# ─────────────────────────────────────────

class TTLCache:
    """
    Thread-safe TTL 캐시.

    Flask 멀티스레드 환경에서 동일 메모리를 공유하므로 Lock을 사용합니다.
    복잡한 외부 라이브러리(redis, memcached) 없이 인프라 의존성을 최소화합니다.

    사용 예:
        cache = TTLCache(ttl=300)  # 5분 캐시
        result = cache.get("market_gate")
        if result is None:
            result = compute_market_gate()
            cache.set("market_gate", result)
    """

    def __init__(self, ttl: int = 300):
        """
        Args:
            ttl: 캐시 유효 시간 (초, 기본 5분)
        """
        self._ttl = ttl
        self._store: Dict[str, Any] = {}
        self._expires: Dict[str, float] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        """키에 해당하는 값을 반환합니다. 만료됐거나 없으면 None."""
        with self._lock:
            if key not in self._store:
                return None
            if time.time() > self._expires[key]:
                del self._store[key]
                del self._expires[key]
                return None
            return self._store[key]

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """키-값을 캐시에 저장합니다."""
        with self._lock:
            self._store[key] = value
            self._expires[key] = time.time() + (ttl or self._ttl)

    def delete(self, key: str) -> None:
        """특정 키를 캐시에서 제거합니다."""
        with self._lock:
            self._store.pop(key, None)
            self._expires.pop(key, None)

    def clear(self) -> None:
        """캐시를 전체 초기화합니다."""
        with self._lock:
            self._store.clear()
            self._expires.clear()


# ─────────────────────────────────────────
# 글로벌 캐시 인스턴스
# ─────────────────────────────────────────

# Market Gate: 15분 캐시 (빈번한 호출 방지)
market_gate_cache = TTLCache(ttl=900)

# VCP 시그널: 5분 캐시
signal_cache = TTLCache(ttl=300)

# 주가 차트: 1분 캐시 (실시간에 가깝게)
chart_cache = TTLCache(ttl=60)
