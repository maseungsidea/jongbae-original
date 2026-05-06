"""KIS OpenAPI 설정 (모의/실전 분기, 계좌번호 파싱).

환경변수:
    KIS_ENV          : "mock" | "prod"  (default: mock)
    KIS_APP_KEY      : OpenAPI App Key
    KIS_APP_SECRET   : OpenAPI App Secret
    KIS_ACCOUNT_NO   : "12345678-01" (종합계좌번호-상품코드)
    KIS_CUSTTYPE     : "P" | "B"  (default: P)
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum


class KISEnv(str, Enum):
    MOCK = "mock"
    PROD = "prod"


# 모의/실전 base URL — KIS 공식 문서 기준
_BASE_URL = {
    KISEnv.MOCK: "https://openapivts.koreainvestment.com:29443",
    KISEnv.PROD: "https://openapi.koreainvestment.com:9443",
}

# TR_ID 매핑: 모의는 V 접두, 실전은 T 접두
TR_IDS = {
    "order_buy":   {KISEnv.MOCK: "VTTC0802U", KISEnv.PROD: "TTTC0802U"},
    "order_sell":  {KISEnv.MOCK: "VTTC0801U", KISEnv.PROD: "TTTC0801U"},
    "balance":     {KISEnv.MOCK: "VTTC8434R", KISEnv.PROD: "TTTC8434R"},
    "psbl_order":  {KISEnv.MOCK: "VTTC8908R", KISEnv.PROD: "TTTC8908R"},
}


@dataclass(frozen=True)
class KISConfig:
    env: KISEnv
    app_key: str
    app_secret: str
    cano: str             # 종합계좌번호 (8자리)
    acnt_prdt_cd: str     # 계좌상품코드 (2자리, 보통 "01")
    custtype: str = "P"

    @property
    def base_url(self) -> str:
        return _BASE_URL[self.env]

    @property
    def is_mock(self) -> bool:
        return self.env == KISEnv.MOCK

    def tr_id(self, key: str) -> str:
        return TR_IDS[key][self.env]

    @classmethod
    def from_env(cls) -> "KISConfig":
        """환경변수에서 설정 로드. 누락 시 ValueError."""
        env_str = os.getenv("KIS_ENV", "mock").lower()
        try:
            env = KISEnv(env_str)
        except ValueError as e:
            raise ValueError(f"KIS_ENV must be 'mock' or 'prod', got {env_str!r}") from e

        app_key = os.getenv("KIS_APP_KEY", "").strip()
        app_secret = os.getenv("KIS_APP_SECRET", "").strip()
        account = os.getenv("KIS_ACCOUNT_NO", "").strip()
        custtype = os.getenv("KIS_CUSTTYPE", "P").strip() or "P"

        missing = [k for k, v in [
            ("KIS_APP_KEY", app_key),
            ("KIS_APP_SECRET", app_secret),
            ("KIS_ACCOUNT_NO", account),
        ] if not v]
        if missing:
            raise ValueError(f"KIS env vars missing: {missing}")

        cano, acnt_prdt_cd = _parse_account(account)
        return cls(
            env=env, app_key=app_key, app_secret=app_secret,
            cano=cano, acnt_prdt_cd=acnt_prdt_cd, custtype=custtype,
        )


def _parse_account(account_no: str) -> tuple[str, str]:
    """'12345678-01' → ('12345678', '01'). 8자리/2자리 검증."""
    parts = account_no.split("-")
    if len(parts) != 2:
        raise ValueError(f"KIS_ACCOUNT_NO must be 'CANO-PRDT' format, got {account_no!r}")
    cano, prdt = parts[0].strip(), parts[1].strip()
    if not (cano.isdigit() and len(cano) == 8):
        raise ValueError(f"CANO must be 8 digits, got {cano!r}")
    if not (prdt.isdigit() and len(prdt) == 2):
        raise ValueError(f"ACNT_PRDT_CD must be 2 digits, got {prdt!r}")
    return cano, prdt
