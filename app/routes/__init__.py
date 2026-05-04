"""
Routes 패키지.
kr_bp (KR 마켓), common_bp (공통) Blueprint를 외부에 노출합니다.
"""
from app.routes.kr_market import kr_bp
from app.routes.common import common_bp

__all__ = ["kr_bp", "common_bp"]
