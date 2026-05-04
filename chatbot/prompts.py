"""
챗봇 시스템 프롬프트 (chatbot/prompts.py)

Gemini LLM에게 전달할 시스템 프롬프트를 관리합니다.
시장 컨텍스트를 동적으로 주입하여 최신 데이터 기반 답변을 유도합니다.

설계 의도:
  프롬프트를 별도 파일로 분리하면 코어 로직 변경 없이
  AI 퍼소나와 지시사항을 쉽게 튜닝할 수 있습니다.
"""

from __future__ import annotations


BASE_SYSTEM_PROMPT = """당신은 '종가봇'입니다. 한국 주식 종가배팅 전략에 특화된 AI 투자 어시스턴트입니다.

## 역할
- 한국 주식(KOSPI/KOSDAQ) 종가베팅 전략 분석 및 조언
- VCP(Volatility Contraction Pattern) 패턴 설명
- 시그널 데이터 해석 및 포지션 관리 안내
- 일반 주식 투자 원칙 (리스크 관리, 손절, 수익실현)

## 응답 원칙
1. 사실 근거 우선: 제공된 시장 데이터(컨텍스트)를 최우선으로 활용할 것
2. 간결명료: 핵심만 3~5줄로 답변, 필요 시 불릿으로 정리
3. 한국어 답변: 모든 답변은 한국어로
4. 투자 책임 고지: 매매 결정은 사용자 본인의 판단임을 명시
5. 불확실성 인정: 모르는 것은 모른다고 솔직히 말할 것

## 하지 말아야 할 것
- 특정 종목 매수/매도 단정적 추천
- 수익률 보장 발언
- KRX 영업 시간 외의 실시간 데이터 주장

---
{market_context}
"""


def build_system_prompt(market_context: str = "") -> str:
    """
    시장 컨텍스트를 주입한 시스템 프롬프트를 반환합니다.

    Args:
        market_context: data_loader.get_market_context() 결과

    Returns:
        완성된 시스템 프롬프트 문자열
    """
    context_section = f"## 현재 시장 데이터\n{market_context}" if market_context else ""
    return BASE_SYSTEM_PROMPT.format(market_context=context_section)


INTENT_KEYWORDS = {
    "market_gate": ["마켓 게이트", "시장 상태", "매수 가능", "GREEN", "YELLOW", "RED"],
    "signals": ["시그널", "신호", "종가베팅", "추천 종목", "오늘 시그널"],
    "performance": ["성과", "수익률", "손익", "승률", "백테스트"],
    "stock_detail": ["차트", "봉", "패턴", "52주", "이평선"],
    "position_sizing": ["포지션", "매수 금액", "비중", "손절가", "목표가"],
}


def detect_intent(message: str) -> str:
    """
    사용자 메시지에서 의도를 감지합니다.

    Args:
        message: 사용자 입력 텍스트

    Returns:
        감지된 의도 키 (매치 없으면 "general")
    """
    for intent, keywords in INTENT_KEYWORDS.items():
        if any(kw in message for kw in keywords):
            return intent
    return "general"
