# Closing Bet 개발 계획서

> **버전**: 1.0
> **작성일**: 2026-02-15
> **상태**: 구현 미착수

---

## 프로젝트 현황 요약

### 현재 상태

| 항목     | 상태                       | 비고                  |
| ------ | ------------------------ | ------------------- |
| 소스 코드  | **없음**                   | `.py`, `.tsx` 파일 0개 |
| 데이터 파일 | **없음**                   | `data/` 디렉토리 빈 상태   |
| 테스트    | **없음**                   | 테스트 프레임워크 미설정       |

---

## 모듈 의존성 다이어그램

```
Phase 0: 프로젝트 스캐폴딩
  └── requirements.txt, .env, 디렉토리 구조

Phase 1: 핵심 기반 모듈
  ├── config.py          (의존성 없음)
  ├── models.py          (의존성 없음)
  ├── engine/config.py   (의존성 없음)
  └── engine/models.py   (의존성 없음)

Phase 2: 데이터 수집 레이어
  ├── engine/collectors.py       ← engine/config.py, engine/models.py
  ├── scripts/create_kr_stock_list.py    (pykrx)
  ├── scripts/create_complete_daily_prices.py (pykrx)
  └── all_institutional_trend_data.py    (pykrx)

Phase 3: 엔진 코어
  ├── engine/scorer.py           ← engine/config.py, engine/models.py
  ├── engine/position_sizer.py   ← engine/config.py
  ├── engine/llm_analyzer.py     ← (google-generativeai)
  └── engine/generator.py        ← scorer, position_sizer, llm_analyzer, collectors

Phase 4: Flask API 서버
  ├── app/__init__.py            ← (Flask factory)
  ├── app/utils/cache.py         (의존성 없음)
  ├── app/routes/kr_market.py    ← engine/generator, market_gate, scheduler
  ├── app/routes/common.py       ← app/utils/cache
  ├── market_gate.py             ← (pykrx, yfinance)
  ├── screener.py                ← config, models
  ├── scheduler.py               ← screener, signal_tracker
  └── flask_app.py               ← app/__init__.py

Phase 5: AI 통합
  ├── chatbot/memory.py          (의존성 없음)
  ├── chatbot/history.py         (의존성 없음)
  ├── chatbot/data_loader.py     ← data/ 파일들
  ├── chatbot/prompts.py         (의존성 없음)
  ├── chatbot/core.py            ← memory, history, prompts, data_loader
  └── chatbot/__init__.py        ← core

Phase 6: 프론트엔드
  ├── frontend/ 스캐폴딩         (Next.js + Tailwind)
  ├── frontend/src/lib/api.ts    (의존성 없음)
  ├── frontend/src/app/globals.css
  ├── frontend/src/app/dashboard/kr/page.tsx         ← api.ts
  ├── frontend/src/app/dashboard/kr/vcp/page.tsx     ← api.ts
  └── frontend/src/app/dashboard/kr/closing-bet/page.tsx ← api.ts

Phase 7: 통합 테스트 및 배포 준비
  └── E2E 검증, 데이터 파이프라인, 배포 설정
```

---

## Phase 0: 프로젝트 스캐폴딩

### 목표
프로젝트 디렉토리 구조, 의존성 파일, 환경 설정 파일을 생성하여 개발 기반을 마련한다.

### 구현 파일 목록

| 파일                                      | 설명                             | 스펙 정의 여부 |
| --------------------------------------- | ------------------------------ | -------- |
| `requirements.txt`                      | Python 의존성 목록                  | 설계 필요    |
| `.env.example`                          | 환경변수 템플릿                       | 설계 필요    |
| `frontend/package.json`                 | Node.js 의존성                    | 설계 필요    |
| `frontend/next.config.js`               | Next.js 설정 (API 프록시 포함)        | 설계 필요    |
| `frontend/tailwind.config.ts`           | Tailwind CSS 설정                | 설계 필요    |
| `frontend/tsconfig.json`                | TypeScript 설정                  | 설계 필요    |
| `app/__init__.py`                       | Flask 앱 팩토리                    | 설계 필요    |
| `app/routes/__init__.py`                | Routes 패키지 init                | 설계 필요    |
| `engine/__init__.py`                    | Engine 패키지 init                | 설계 필요    |
| `chatbot/__init__.py`                   | Chatbot 패키지 init (get_chatbot) | 설계 필요    |
| `frontend/src/app/layout.tsx`           | Next.js 루트 레이아웃                | 설계 필요    |
| `frontend/src/app/dashboard/layout.tsx` | 대시보드 레이아웃 (사이드바)               | 설계 필요    |

### 디렉토리 구조

```
closing-bet/
├── app/
│   ├── __init__.py
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── kr_market.py
│   │   └── common.py
│   └── utils/
│       └── cache.py
├── engine/
│   ├── __init__.py
│   ├── config.py
│   ├── models.py
│   ├── collectors.py
│   ├── scorer.py
│   ├── position_sizer.py
│   ├── llm_analyzer.py
│   └── generator.py
├── chatbot/
│   ├── __init__.py
│   ├── core.py
│   ├── prompts.py
│   ├── memory.py
│   ├── history.py
│   └── data_loader.py
├── scripts/
│   ├── create_kr_stock_list.py
│   └── create_complete_daily_prices.py
├── data/
│   └── (생성된 CSV/JSON)
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx
│   │   │   ├── globals.css
│   │   │   └── dashboard/
│   │   │       ├── layout.tsx
│   │   │       └── kr/
│   │   │           ├── page.tsx
│   │   │           ├── vcp/page.tsx
│   │   │           └── closing-bet/page.tsx
│   │   └── lib/
│   │       └── api.ts
│   ├── package.json
│   ├── next.config.js
│   ├── tailwind.config.ts
│   └── tsconfig.json
├── flask_app.py
├── config.py
├── models.py
├── run.py
├── market_gate.py
├── screener.py
├── scheduler.py
├── signal_tracker.py
├── all_institutional_trend_data.py
├── requirements.txt
├── .env.example
└── .gitignore
```

### 핵심 클래스/함수

```python
# app/__init__.py
def create_app() -> Flask:
    """Flask 앱 팩토리 - Blueprint 등록, CORS 설정"""
    ...
```

```python
# chatbot/__init__.py
_chatbot_instance = None

def get_chatbot() -> KRStockChatbot:
    """싱글턴 챗봇 인스턴스 반환"""
    ...
```

### 의존성
- 없음 (최초 Phase)

### 검증 방법

```bash
# Python 의존성 설치 확인
pip install -r requirements.txt
python -c "import flask; import pykrx; import pandas; print('OK')"

# 디렉토리 구조 확인
find . -name "*.py" -o -name "*.tsx" -o -name "*.ts" | head -30

# Frontend 의존성 설치 확인
cd frontend && npm install && npm run build
```

### 예상 산출물
- 전체 디렉토리 구조 (`__init__.py` 파일 포함)
- `requirements.txt`, `.env.example`
- `frontend/` 기본 Next.js 프로젝트 (빈 페이지 렌더링 가능)
- `app/__init__.py` Flask 팩토리 (빈 서버 구동 가능)

---

## Phase 1: 핵심 기반 모듈 (Config, Models)

### 목표
시스템 전체에서 사용하는 설정(Config)과 데이터 모델(Models)을 구현한다. 다른 모든 모듈의 기반이 된다.

### 구현 파일 목록

| 파일                 | 설명                                                      | 스펙 정의 여부 |
| ------------------ | ------------------------------------------------------- | -------- |
| `config.py`        | 루트 설정 (MarketRegime, TrendThresholds, BacktestConfig 등) | 설계 필요    |
| `models.py`        | 루트 데이터 모델 (StockInfo, Signal, Trade, BacktestResult 등)  | 설계 필요    |
| `engine/config.py` | 엔진 설정 (Grade, SignalConfig, GradeConfig)                | 설계 필요    |
| `engine/models.py` | 엔진 데이터 모델 (StockData, Signal, ScoreDetail 등)            | 설계 필요    |

### 핵심 클래스/함수

```python
# config.py - 사용자 요구 반영
class MarketRegime(Enum): ...
class SignalType(Enum): ...

@dataclass
class TrendThresholds: ...
@dataclass
class MarketGateConfig: ...
@dataclass
class BacktestConfig:
    def get_total_cost_pct(self) -> float: ...
    def should_trade_in_regime(self, regime: str) -> bool: ...
    @classmethod
    def conservative(cls) -> "BacktestConfig": ...
    @classmethod
    def aggressive(cls) -> "BacktestConfig": ...
@dataclass
class ScreenerConfig: ...
```

```python
# models.py - 사용자 요구 반영
@dataclass
class StockInfo: ...
@dataclass
class InstitutionalFlow: ...
@dataclass
class TrendAnalysis:
    def to_dict(self) -> Dict: ...
@dataclass
class Signal:
    def to_dict(self) -> Dict: ...
@dataclass
class Trade:
    @property
    def is_closed(self) -> bool: ...
    @property
    def return_pct(self) -> float: ...
    @property
    def pnl(self) -> float: ...
    @property
    def r_multiple(self) -> float: ...
@dataclass
class BacktestResult:
    def to_dict(self) -> Dict: ...
@dataclass
class MarketStatus:
    def to_dict(self) -> Dict: ...
```

```python
# engine/config.py - 사용자 요구 반영
class Grade(Enum): S, A, B, C
@dataclass
class GradeConfig: ...
@dataclass
class SignalConfig:
    # 기본 필터, 제외 조건, 점수 가중치, 등급별 기준,
    # 매매 설정, 리스크 관리, 뉴스 키워드
    ...
```

```python
# engine/models.py - 설계 필요
# generator.py의 import에서 참조되는 클래스들:
@dataclass
class StockData:
    code: str
    name: str
    market: str       # KOSPI / KOSDAQ
    sector: str
    close: float      # 현재가
    change_pct: float # 등락률
    trading_value: int # 거래대금
    volume: int
    marcap: int       # 시가총액
    high_52w: Optional[float] = None

@dataclass
class NewsItem:
    title: str
    summary: str
    source: str
    url: str
    published_at: Optional[datetime] = None

@dataclass
class SupplyData:
    foreign_buy_5d: int = 0
    inst_buy_5d: int = 0

@dataclass
class ChartData:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int

@dataclass
class ScoreDetail:
    news: int = 0
    volume: int = 0
    chart: int = 0
    candle: int = 0
    consolidation: int = 0
    supply: int = 0
    llm_reason: str = ""
    @property
    def total(self) -> int: ...

@dataclass
class ChecklistDetail:
    has_news: bool = False
    news_sources: List[str] = field(default_factory=list)
    is_new_high: bool = False
    is_breakout: bool = False
    supply_positive: bool = False
    volume_surge: bool = False

class SignalStatus(Enum):
    PENDING = "pending"
    ENTERED = "entered"
    EXITED = "exited"

@dataclass
class Signal:
    stock_code: str
    stock_name: str
    market: str
    sector: str
    signal_date: date
    signal_time: datetime
    grade: Grade
    score: ScoreDetail
    checklist: ChecklistDetail
    news_items: List[Dict]
    current_price: float
    entry_price: float
    stop_price: float
    target_price: float
    r_value: float
    position_size: float
    quantity: int
    r_multiplier: float
    trading_value: int
    change_pct: float
    status: SignalStatus
    created_at: datetime
    def to_dict(self) -> Dict: ...

@dataclass
class ScreenerResult:
    date: date
    total_candidates: int
    filtered_count: int
    signals: List[Signal]
    by_grade: Dict[str, int]
    by_market: Dict[str, int]
    processing_time_ms: float
```

### 의존성
- Phase 0 완료 (디렉토리 구조, `__init__.py`)
- Python 표준 라이브러리만 사용 (`dataclasses`, `enum`, `typing`)

### 검증 방법

```bash
# 임포트 테스트
python -c "from config import MarketRegime, BacktestConfig; print(BacktestConfig.conservative())"
python -c "from models import Signal, Trade; print('OK')"
python -c "from engine.config import Grade, SignalConfig; print(SignalConfig())"
python -c "from engine.models import StockData, ScoreDetail; print(ScoreDetail().total)"
```

### 예상 산출물
- `config.py` (216줄)
- `models.py` (593줄)
- `engine/config.py` (177줄)
- `engine/models.py` (~200줄, 새로 설계)

---

## Phase 2: 데이터 수집 레이어 (Collectors, Scripts)

### 목표
KRX/네이버에서 주가, 수급, 뉴스 데이터를 수집하는 모듈과 초기 데이터 생성 스크립트를 구현한다.

### 구현 파일 목록

| 파일 | 설명 | 스펙 정의 여부 |
|------|------|----------------|
| `engine/collectors.py` | KRXCollector, EnhancedNewsCollector | 설계 필요 (시그니처 추론 가능) |
| `scripts/create_kr_stock_list.py` | 한국 주식 전 종목 목록 생성 | 설계 필요 |
| `scripts/create_complete_daily_prices.py` | 2년치 일봉 데이터 CSV 생성 | 설계 필요 |
| `all_institutional_trend_data.py` | 기관/외인 수급 데이터 CSV 생성 | 설계 필요 |
| `signal_tracker.py` | VCP 시그널 추적 및 CSV 저장 | 설계 필요 |

### 핵심 클래스/함수

```python
# engine/collectors.py - generator.py에서 추론한 인터페이스
class KRXCollector:
    """pykrx 기반 KRX 데이터 수집기"""
    def __init__(self, config: SignalConfig): ...
    async def __aenter__(self): ...
    async def __aexit__(self, ...): ...
    async def get_top_gainers(self, market: str, top_n: int) -> List[StockData]: ...
    async def get_stock_detail(self, code: str) -> Optional[StockData]: ...
    async def get_chart_data(self, code: str, days: int) -> List[ChartData]: ...
    async def get_supply_data(self, code: str) -> Optional[SupplyData]: ...

class EnhancedNewsCollector:
    """네이버/다음 뉴스 크롤링 수집기"""
    def __init__(self, config: SignalConfig): ...
    async def __aenter__(self): ...
    async def __aexit__(self, ...): ...
    async def get_stock_news(
        self, code: str, limit: int, name: str
    ) -> List[NewsItem]: ...
```

```python
# scripts/create_kr_stock_list.py
def create_stock_list() -> None:
    """pykrx로 KOSPI+KOSDAQ 전 종목 → data/korean_stocks_list.csv"""
    # 출력: ticker, name, market, sector
    ...

# scripts/create_complete_daily_prices.py
def create_daily_prices(days: int = 730) -> None:
    """전 종목 2년치 OHLCV → data/daily_prices.csv"""
    # 출력: ticker, date, open, high, low, current_price, volume
    ...

# all_institutional_trend_data.py
def collect_institutional_data() -> None:
    """전 종목 60일 수급 데이터 → data/all_institutional_trend_data.csv"""
    # 출력: ticker, date, foreign_net_buy, inst_net_buy, ...
    ...

# signal_tracker.py
def track_signals() -> None:
    """수급+VCP 조건 충족 종목 탐지 → signals_log.csv"""
    ...
```

### 의존성
- Phase 1 완료 (`engine/config.py`, `engine/models.py`)
- 외부 라이브러리: `pykrx`, `pandas`, `aiohttp`, `beautifulsoup4`

### 검증 방법

```bash
# 1. 종목 리스트 생성
python scripts/create_kr_stock_list.py
ls -la data/korean_stocks_list.csv
python -c "import pandas as pd; df=pd.read_csv('data/korean_stocks_list.csv'); print(f'{len(df)}개 종목')"

# 2. 일봉 데이터 생성 (시간 소요: ~5분)
python scripts/create_complete_daily_prices.py
python -c "import pandas as pd; df=pd.read_csv('data/daily_prices.csv', dtype={'ticker':str}); print(f'{len(df)}행')"

# 3. 수급 데이터 생성 (시간 소요: ~5분)
python all_institutional_trend_data.py
ls -la data/all_institutional_trend_data.csv

# 4. Collector 단위 테스트
python -c "
import asyncio
from engine.collectors import KRXCollector
from engine.config import SignalConfig
async def test():
    async with KRXCollector(SignalConfig()) as c:
        gainers = await c.get_top_gainers('KOSPI', 5)
        print(f'Top gainers: {len(gainers)}개')
asyncio.run(test())
"
```

### 예상 산출물
- `engine/collectors.py` (~400줄, 새로 설계)
- `scripts/create_kr_stock_list.py` (~80줄)
- `scripts/create_complete_daily_prices.py` (~120줄)
- `all_institutional_trend_data.py` (~150줄)
- `signal_tracker.py` (~200줄)
- `data/korean_stocks_list.csv` (~2,500개 종목)
- `data/daily_prices.csv` (~120MB)
- `data/all_institutional_trend_data.csv` (~50MB)

---

## Phase 3: 엔진 코어 (Scorer, PositionSizer, LLM)

### 목표
종가베팅 V2의 핵심 분석 엔진을 구현한다: 12점 채점 시스템, 자금 관리, LLM 뉴스 분석, 시그널 생성 오케스트레이터.

### 구현 파일 목록

| 파일                         | 설명                  | 스펙 정의 여부           |
| -------------------------- | ------------------- | ------------------ |
| `engine/scorer.py`         | 12점 채점 시스템 (6개 항목)  | 설계 필요              |
| `engine/position_sizer.py` | 포지션 사이징 및 리스크 관리    | 설계 필요 (시그니처 추론 가능) |
| `engine/llm_analyzer.py`   | Gemini LLM 뉴스 감성 분석 | 설계 필요              |
| `engine/generator.py`      | 시그널 생성 오케스트레이터      | 설계 필요              |

### 핵심 클래스/함수

```python
# engine/scorer.py - 설계 필요
class Scorer:
    """12점 만점 종가베팅 채점 시스템"""
    def __init__(self, config: SignalConfig): ...

    def calculate(
        self,
        stock: StockData,
        charts: List[ChartData],
        news: List[NewsItem],
        supply: Optional[SupplyData],
        llm_result: Optional[Dict],
    ) -> Tuple[ScoreDetail, ChecklistDetail]:
        """
        6개 항목 채점:
        - 뉴스/재료: 0~3점 (LLM 기반, 키워드 폴백)
        - 거래대금: 0~3점 (1조→3, 5천억→2, 1천억→1)
        - 차트패턴: 0~2점 (신고가, 이평선 정배열)
        - 캔들형태: 0~1점 (장대양봉, 윗꼬리 짧음)
        - 기간조정: 0~1점 (횡보 후 돌파, 볼린저 수축)
        - 수급:     0~2점 (외인+기관 순매수)
        """
        ...

    def determine_grade(self, stock: StockData, score: ScoreDetail) -> Grade:
        """
        등급 결정:
        - S: 10점+ & 거래대금 1조+
        - A: 8점+ & 거래대금 5천억+
        - B: 6점+ & 거래대금 1천억+
        - C: 그 외 (제외)
        """
        ...

    # 내부 채점 메서드
    def _score_news(self, news: List[NewsItem], llm_result: Optional[Dict]) -> int: ...
    def _score_volume(self, trading_value: int) -> int: ...
    def _score_chart(self, stock: StockData, charts: List[ChartData]) -> int: ...
    def _score_candle(self, stock: StockData, charts: List[ChartData]) -> int: ...
    def _score_consolidation(self, charts: List[ChartData]) -> int: ...
    def _score_supply(self, supply: Optional[SupplyData]) -> int: ...
```

```python
# engine/position_sizer.py - 설계 필요
@dataclass
class PositionResult:
    entry_price: float
    stop_price: float
    target_price: float
    r_value: float          # 1R 금액
    position_size: float    # 투자 금액
    quantity: int           # 매수 수량
    r_multiplier: float     # R 배수

class PositionSizer:
    """자금 관리 및 포지션 사이징"""
    def __init__(self, capital: float, config: SignalConfig): ...

    def calculate(self, price: float, grade: Grade) -> PositionResult:
        """
        - entry_price = 현재가
        - stop_price = 현재가 * (1 - stop_loss_pct)  # -3%
        - target_price = 현재가 * (1 + take_profit_pct) # +5%
        - r_value = capital * r_ratio (0.5%)
        - position_size = r_value * r_multiplier / risk_per_share
        - quantity = position_size / price
        """
        ...
```

```python
# engine/llm_analyzer.py - 설계 필요
class LLMAnalyzer:
    def __init__(self, api_key: str = None): ...
    async def analyze_news_sentiment(
        self, stock_name: str, news_items: List[Dict]
    ) -> Dict:
        """뉴스 → 호재 점수(0~3) + 요약"""
        ...
```

```python
# engine/generator.py - 설계 필요
class SignalGenerator:
    def __init__(self, config: SignalConfig = None, capital: float = 10_000_000): ...
    async def __aenter__(self): ...
    async def __aexit__(self, ...): ...
    async def generate(
        self, target_date: date = None, markets: List[str] = None, top_n: int = 30
    ) -> List[Signal]: ...
    async def _analyze_stock(self, stock: StockData, target_date: date) -> Optional[Signal]: ...
    def get_summary(self, signals: List[Signal]) -> Dict: ...

async def run_screener(capital: float = 50_000_000, ...) -> ScreenerResult: ...
async def analyze_single_stock_by_code(code: str, ...) -> Optional[Signal]: ...
def save_result_to_json(result: ScreenerResult) -> None: ...
```

### 의존성
- Phase 1 완료 (config, models)
- Phase 2 완료 (collectors)
- 외부 라이브러리: `google-generativeai`, `python-dotenv`

### 검증 방법

```bash
# 1. Scorer 단위 테스트
python -c "
from engine.scorer import Scorer
from engine.config import SignalConfig
from engine.models import StockData, ScoreDetail
scorer = Scorer(SignalConfig())
print('Scorer initialized OK')
"

# 2. PositionSizer 테스트
python -c "
from engine.position_sizer import PositionSizer
from engine.config import SignalConfig, Grade
ps = PositionSizer(50_000_000, SignalConfig())
result = ps.calculate(10000, Grade.A)
print(f'Entry: {result.entry_price}, Stop: {result.stop_price}, Qty: {result.quantity}')
"

# 3. LLM Analyzer 테스트 (API 키 필요)
python -c "
from engine.llm_analyzer import LLMAnalyzer
analyzer = LLMAnalyzer()
print(f'Model: {analyzer.model is not None}')
"

# 4. 전체 엔진 실행 (E2E)
python -c "
from engine.generator import run_screener
import asyncio
result = asyncio.run(run_screener(capital=50_000_000))
print(f'Signals: {len(result.signals)}, Time: {result.processing_time_ms:.0f}ms')
"
```

### 예상 산출물
- `engine/scorer.py` (~250줄, 새로 설계)
- `engine/position_sizer.py` (~100줄, 새로 설계)
- `engine/llm_analyzer.py` (~150줄, 새로 설계)
- `engine/generator.py` (~500줄, 새로 설계)
- `data/jongga_v2_latest.json` (엔진 실행 시 생성)

---

## Phase 4: Flask API 서버 (Routes, MarketGate, Screener)

### 목표
Flask REST API 서버를 구현한다. KR 마켓 22개 엔드포인트, 공통 8개 엔드포인트, Market Gate, VCP 스크리너를 포함한다.

### 구현 파일 목록

| 파일                        | 설명                                | 스펙 정의 여부 |
| ------------------------- | --------------------------------- | -------- |
| `app/__init__.py`         | Flask 앱 팩토리                       | 설계 필요    |
| `app/utils/cache.py`      | 섹터 캐시 유틸 (get_sector, SECTOR_MAP) | 설계 필요    |
| `app/routes/kr_market.py` | KR 마켓 API 엔드포인트(아래 내용 참조)         | 설계 필요    |
| `app/routes/common.py`    | 공통 API 8개 엔드포인트                   | 설계 필요    |
| `market_gate.py`          | 시장 상태 분석 (섹터 ETF 기반)              | 설계 필요    |
| `screener.py`             | VCP + 수급 스크리너                     | 설계 필요    |
| `scheduler.py`            | 자동 데이터 업데이트 스케줄러                  | 설계 필요    |
| `flask_app.py`            | 서버 진입점                            | 설계 필요    |
| `run.py`                  | CLI 진입점                           | 설계 필요    |

### 핵심 클래스/함수

```python
# app/__init__.py - 설계 필요
def create_app() -> Flask:
    """
    Flask 앱 팩토리:
    1. Flask() 생성
    2. CORS 설정
    3. kr_bp 등록 (url_prefix='/api/kr')
    4. common_bp 등록 (url_prefix='/api')
    5. health check 엔드포인트
    """
    ...
```

```python
# app/utils/cache.py - 설계 필요
SECTOR_MAP: Dict[str, str] = {
    "005930": "반도체", "000660": "반도체",
    "373220": "2차전지", ...
}

def get_sector(ticker: str) -> str:
    """종목 섹터 반환"""
    ...
```

```python
# market_gate.py - 설계 필요
@dataclass
class SectorResult:
    name: str
    signal: str       # bullish, bearish, neutral
    change_1d: float
    score: int

@dataclass
class MarketGateResult:
    gate: str         # GREEN, YELLOW, RED
    score: int        # 0-100
    reasons: List[str]
    sectors: List[SectorResult]
    metrics: Dict[str, float]

def run_kr_market_gate() -> MarketGateResult:
    """
    분석 지표 (총 100점):
    - 추세 정렬 (EMA20 > EMA60): 25점
    - RSI (50-70 최적): 25점
    - MACD (골든크로스): 20점
    - 거래량 (20일 평균 대비): 15점
    - 상대강도 (RS): 15점

    섹터 ETF 7개 분석:
    - KOSPI200, 반도체, 2차전지, 자동차, IT, 은행, 철강
    """
    ...
```

```python
# screener.py - 설계 필요
class SmartMoneyScreener:
    """VCP + 수급 스크리너 (100점 만점)"""
    def __init__(self): ...
    def run_screening(self, max_stocks: int = 50) -> pd.DataFrame: ...
    def generate_signals(self, results: pd.DataFrame) -> List[Dict]: ...
    def detect_vcp_pattern(self, df: pd.DataFrame) -> float: ...
    def _calculate_score(self, stock_data: Dict) -> float: ...
```

```python
# scheduler.py - 설계 필요
def run_vcp_scan() -> Dict: ...
def run_full_update() -> Dict: ...
def main() -> None:
    """--now 플래그 시 즉시 실행, 아니면 주기적 스케줄"""
    ...
```

### API 엔드포인트 총괄

#### KR Market (`/api/kr/`)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/market-status` | 시장 상태 (MA200 기반) |
| GET | `/signals` | VCP 시그널 목록 |
| GET | `/stock-chart/<ticker>` | 종목 차트 OHLCV |
| GET | `/ai-summary/<ticker>` | AI 종목 요약 |
| GET | `/ai-analysis` | AI 분석 전체 |
| GET | `/ai-history-dates` | AI 히스토리 날짜 |
| GET | `/ai-history/<date>` | 특정 날짜 AI 분석 |
| GET | `/cumulative-return` | 누적 수익률 |
| GET | `/performance` | 퍼포먼스 |
| POST | `/vcp-scan` | VCP 스캔 실행 |
| POST | `/update` | 데이터 업데이트 |
| GET | `/market-gate` | Market Gate 상태 |
| POST | `/realtime-prices` | 실시간 가격 조회 |
| POST | `/chatbot` | 챗봇 대화 |
| GET | `/chatbot/welcome` | 챗봇 웰컴 메시지 |
| GET/POST/DELETE | `/chatbot/memory` | 챗봇 메모리 관리 |
| GET/DELETE | `/chatbot/history` | 챗봇 히스토리 |
| GET | `/chatbot/status` | 챗봇 상태 |
| GET | `/jongga-v2/latest` | 종가베팅 V2 최신 |
| GET | `/jongga-v2/dates` | 날짜 목록 |
| GET | `/jongga-v2/history/<date>` | 히스토리 조회 |
| POST | `/jongga-v2/analyze` | 단일 종목 재분석 |
| POST | `/jongga-v2/run` | 전체 엔진 실행 |

#### Common (`/api/`)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/portfolio` | 포트폴리오 데이터 |
| GET | `/portfolio-summary` | 포트폴리오 요약 |
| GET | `/stock/<ticker>` | 종목 상세 (yfinance) |
| POST | `/realtime-prices` | 실시간 가격 (KR/US) |
| POST | `/run-analysis` | 분석 스크립트 실행 |
| GET | `/system/data-status` | 데이터 파일 상태 |
| GET | `/system/update-data-stream` | SSE 업데이트 스트림 |
| GET | `/kr/backtest-summary` | 백테스트 요약 |

### 의존성
- Phase 0~3 모두 완료
- 외부 라이브러리: `flask`, `flask-cors`, `pandas`, `yfinance`, `pykrx`

### 검증 방법

```bash
# 1. Flask 서버 기동 테스트
python flask_app.py &
sleep 3

# 2. Health check
curl http://localhost:5001/api/health

# 3. Market Gate
curl http://localhost:5001/api/kr/market-gate

# 4. 종가베팅 최신 데이터
curl http://localhost:5001/api/kr/jongga-v2/latest

# 5. 시스템 데이터 상태
curl http://localhost:5001/api/system/data-status

# 서버 종료
kill %1
```

### 예상 산출물
- `app/__init__.py` (~40줄)
- `app/utils/cache.py` (~30줄)
- `app/routes/kr_market.py` (~800줄)
- `app/routes/common.py` (~800줄, 새로 설계)
- `market_gate.py` (~300줄, 새로 설계)
- `screener.py` (~400줄, 새로 설계)
- `scheduler.py` (~200줄, 새로 설계)
- `flask_app.py` (~30줄, 새로 설계)
- `run.py` (~350줄, 새로 설계)

---

## Phase 5: AI 통합 (Chatbot)

### 목표
Gemini 기반 AI 챗봇 모듈을 구현한다. 장기 메모리, 대화 히스토리, 시장 데이터 연동 기능을 포함한다.

### 구현 파일 목록

| 파일                       | 설명                         | 스펙 정의 여부 |
| ------------------------ | -------------------------- | -------- |
| `chatbot/__init__.py`    | get_chatbot 싱글턴            | 설계 필요    |
| `chatbot/memory.py`      | MemoryManager (JSON 파일 기반) | 설계 필요    |
| `chatbot/history.py`     | HistoryManager (최근 10개 대화) | 설계 필요    |
| `chatbot/data_loader.py` | 시장 데이터 로더                  | 설계 필요    |
| `chatbot/prompts.py`     | 시스템 프롬프트 (VCP 전략 특화)       | 설계 필요    |
| `chatbot/core.py`        | KRStockChatbot 메인 클래스      | 설계 필요    |

### 핵심 클래스/함수

```python
# chatbot/memory.py - 설계 필요
class MemoryManager:
    """JSON 파일 기반 장기 메모리"""
    def __init__(self, user_id: str): ...
    def add(self, key: str, value: str) -> str: ...
    def remove(self, key: str) -> str: ...
    def update(self, key: str, value: str) -> str: ...
    def clear(self) -> str: ...
    def view(self) -> Dict: ...
    def format_for_prompt(self) -> str: ...
    def to_dict(self) -> Dict: ...
```

```python
# chatbot/history.py - 설계 필요
class HistoryManager:
    """대화 히스토리 관리 (최근 10개)"""
    def __init__(self, user_id: str): ...
    def add(self, role: str, content: str) -> None: ...
    def get_recent(self, limit: int = 10) -> List[Dict]: ...
    def clear(self) -> str: ...
    def count(self) -> int: ...
    def to_dict(self) -> Dict: ...
```

```python
# chatbot/data_loader.py - 설계 필요
def fetch_all_data() -> Dict[str, Any]:
    """
    data/ 디렉토리에서 시장 데이터 로드:
    - market: KOSPI/KOSDAQ 지수, 환율, Market Gate
    - vcp_stocks: 수급 점수 상위 종목 리스트
    - sector_scores: 섹터별 점수
    """
    ...

def search_stock(query: str) -> Optional[Dict]: ...
def get_top_vcp_stocks(n: int = 3) -> List[Dict]: ...
```

```python
# chatbot/core.py - 설계 필요
class KRStockChatbot:
    def __init__(self, user_id: str, data_fetcher=None, api_key=None): ...
    def chat(self, user_message: str) -> str: ...
    def _call_gemini(self, system_prompt, user_message, chat_history) -> str: ...
    def _fallback_response(self, user_message, vcp_data) -> str: ...
    def _detect_stock_query(self, message) -> Optional[str]: ...
    def _handle_command(self, command) -> str: ...
    def get_welcome(self) -> str: ...
    def to_dict(self) -> Dict: ...
```

### 의존성
- Phase 1 완료 (models)
- Phase 2 완료 (data 파일 존재)
- Phase 4 완료 (챗봇 API 엔드포인트 kr_market.py에 포함)
- 외부 라이브러리: `google-generativeai`

### 검증 방법

```bash
# 1. 챗봇 초기화 테스트
python -c "
from chatbot import get_chatbot
bot = get_chatbot()
print(bot.get_welcome())
"

# 2. 대화 테스트
python -c "
from chatbot import get_chatbot
bot = get_chatbot()
response = bot.chat('오늘 뭐 살까?')
print(response)
"

# 3. 메모리 테스트
python -c "
from chatbot import get_chatbot
bot = get_chatbot()
print(bot.chat('/memory add 투자성향 공격적'))
print(bot.chat('/memory view'))
"

# 4. Flask API를 통한 테스트
curl -X POST http://localhost:5001/api/kr/chatbot \
  -H 'Content-Type: application/json' \
  -d '{"message": "삼성전자 어때?"}'
```

### 예상 산출물
- `chatbot/__init__.py` (~20줄)
- `chatbot/memory.py` (~100줄, 새로 설계)
- `chatbot/history.py` (~80줄, 새로 설계)
- `chatbot/data_loader.py` (~120줄, 새로 설계)
- `chatbot/prompts.py` (~180줄, 새로 설계)
- `chatbot/core.py` (~500줄, 새로 설계)

---

## Phase 6: 프론트엔드 (Next.js Dashboard)

### 목표
Next.js App Router 기반 대시보드를 구현한다. KR 마켓 오버뷰, VCP 시그널, 종가베팅 V2 페이지를 포함한다.

### 구현 파일 목록

| 파일                                                   | 설명                     | 스펙 정의 여부 |
| ---------------------------------------------------- | ---------------------- | -------- |
| `frontend/src/lib/api.ts`                            | API 클라이언트 + 타입 정의      | 설계 필요    |
| `frontend/src/app/globals.css`                       | 디자인 시스템 CSS            | 설계 필요    |
| `frontend/src/app/layout.tsx`                        | 루트 레이아웃                | 설계 필요    |
| `frontend/src/app/dashboard/layout.tsx`              | 대시보드 레이아웃 (사이드바 내비게이션) | 설계 필요    |
| `frontend/src/app/dashboard/kr/page.tsx`             | KR 마켓 오버뷰              | 설게 필요    |
| `frontend/src/app/dashboard/kr/vcp/page.tsx`         | VCP 시그널 테이블            | 설계 필요    |
| `frontend/src/app/dashboard/kr/closing-bet/page.tsx` | 종가베팅 V2 카드 그리드         | 설계 필요    |
| `frontend/next.config.js`                            | Next.js 설정 (Flask 프록시) | 설계 필요    |

### 핵심 컴포넌트/함수

```typescript
// frontend/src/lib/api.ts - 설계 필요
export async function fetchAPI<T>(endpoint: string): Promise<T>
export interface KRSignal { ... }
export interface KRMarketGate { ... }
export interface KRAIAnalysis { ... }
export const krAPI = {
    getSignals, getMarketGate, getAIAnalysis,
    getStockChart, getHistoryDates, getHistory
}
export const closingBetAPI = { getCandidates, getTiming, getBacktestStats }
```

```tsx
// frontend/src/app/dashboard/kr/page.tsx - 설계 필요
export default function KRMarketOverview() { ... }
// - Market Gate 원형 스코어
// - KOSPI 200 섹터 인덱스 그리드
// - KPI 카드 (시그널 수, VCP/Closing Bet 성과)
// - KOSPI/KOSDAQ 지수 카드
```

```tsx
// frontend/src/app/dashboard/kr/vcp/page.tsx - 설계 필요
export default function VCPSignalsPage() { ... }
// - 실시간 가격 업데이트 (60초 간격)
// - 시그널 테이블 (외인/기관 수급, 점수, GPT/Gemini 배지)
```

```tsx
// frontend/src/app/dashboard/kr/closing-bet/page.tsx - 설계 필요
export default function JonggaV2Page() { ... }
// 하위 컴포넌트:
function NaverChartWidget({ symbol }: { symbol: string })
function ChartModal({ symbol, name, onClose })
function SignalCard({ signal, index, onOpenChart })
function ScoreBar({ label, score, max })
function StatBox({ label, value, highlight?, customValue? })
function DataStatusBox({ updatedAt })
```

```tsx
// frontend/src/app/dashboard/layout.tsx - 설계 필요
export default function DashboardLayout({ children }) {
    // 사이드바 내비게이션:
    // - KR Market Overview → /dashboard/kr
    // - VCP Signals → /dashboard/kr/vcp
    // - Closing Bet V2 → /dashboard/kr/closing-bet
    ...
}
```

```javascript
// frontend/next.config.js - 설계 필요
module.exports = {
    async rewrites() {
        return [
            {
                source: '/api/:path*',
                destination: 'http://localhost:5001/api/:path*',
            },
        ];
    },
};
```

### 디자인 시스템 토큰

```
배경:     bg-[#1c1c1e] (서피스), #000000 (페이지)
테두리:    border-white/10
텍스트:    text-white (제목), text-gray-400 (본문), text-gray-500 (보조)
등급 색상:
  S → indigo-500 (bg-indigo-500/10 text-indigo-400)
  A → rose-500
  B → blue-500
  C → gray-500
강세/약세:  text-green-400 (상승), text-red-400 (하락)
한국 관례:  text-rose-400 (상승), text-blue-400 (하락)
```

### 의존성
- Phase 0 완료 (Next.js 스캐폴딩)
- Phase 4 완료 (Flask API 서버 가동)
- npm 패키지: `next`, `react`, `typescript`, `tailwindcss`, `@tailwindcss/postcss`

### 검증 방법

```bash
# 1. 빌드 테스트
cd frontend && npm run build

# 2. Lint 테스트
cd frontend && npm run lint

# 3. 개발 서버 실행
cd frontend && npm run dev &

# 4. 페이지 접근 테스트 (Flask + Next.js 동시 실행 필요)
curl http://localhost:3000/dashboard/kr
curl http://localhost:3000/dashboard/kr/vcp
curl http://localhost:3000/dashboard/kr/closing-bet

# 5. API 프록시 테스트
curl http://localhost:3000/api/health
```

### 예상 산출물
- `frontend/src/lib/api.ts` (~120줄, 새로 설계)
- `frontend/src/app/globals.css` (~140줄, 새로 설계)
- `frontend/src/app/layout.tsx` (~30줄, 새로 설계)
- `frontend/src/app/dashboard/layout.tsx` (~100줄, 새로 설계)
- `frontend/src/app/dashboard/kr/page.tsx` (~300줄, 새로 설계)
- `frontend/src/app/dashboard/kr/vcp/page.tsx` (~1000줄, 새로 설계)
- `frontend/src/app/dashboard/kr/closing-bet/page.tsx` (~800줄, 새로 설계계)
- `frontend/next.config.js` (~15줄, 새로 설계)

---

## Phase 7: 통합 테스트 및 배포 준비

### 목표
전체 시스템 E2E 검증, 데이터 파이프라인 확인, 배포 설정을 완료한다.

### 구현/설정 파일 목록

| 파일 | 설명 | 스펙 정의 여부 |
|------|------|----------------|
| `.gitignore` | Git 제외 규칙 | 설계 필요 |
| `Procfile` / `railway.toml` | 배포 설정 (Railway 등) | 설계 필요 |
| `gunicorn.conf.py` | Gunicorn 프로덕션 설정 | 설계 필요 |
| 테스트 스크립트 | 수동 E2E 테스트 명령어 | 설계 필요 |

### 검증 시나리오

#### 1. 데이터 파이프라인 E2E

```bash
# 전체 데이터 생성 순서 테스트
python scripts/create_kr_stock_list.py
python scripts/create_complete_daily_prices.py
python all_institutional_trend_data.py
python signal_tracker.py

# 데이터 파일 존재 확인
ls -la data/korean_stocks_list.csv
ls -la data/daily_prices.csv
ls -la data/all_institutional_trend_data.csv
```

#### 2. 엔진 E2E

```bash
# 종가베팅 V2 엔진 실행
python -m engine.generator
# 기대: data/jongga_v2_latest.json 생성

# VCP 스크리너 실행
python -m screener
# 기대: signals_log.csv 생성/갱신
```

#### 3. API 서버 E2E

```bash
# Flask 서버 기동
python flask_app.py &
sleep 3

# 핵심 엔드포인트 테스트
curl -s http://localhost:5001/api/health | python -m json.tool
curl -s http://localhost:5001/api/kr/market-gate | python -m json.tool
curl -s http://localhost:5001/api/kr/signals | python -m json.tool
curl -s http://localhost:5001/api/kr/jongga-v2/latest | python -m json.tool
curl -s http://localhost:5001/api/system/data-status | python -m json.tool

# 챗봇 테스트
curl -s -X POST http://localhost:5001/api/kr/chatbot \
  -H 'Content-Type: application/json' \
  -d '{"message": "오늘 뭐 살까?"}' | python -m json.tool
```

#### 4. 프론트엔드 E2E

```bash
# Next.js 빌드 + 실행
cd frontend && npm run build && npm start &
sleep 5

# 페이지 렌더링 확인
curl -s http://localhost:3000/dashboard/kr | head -20
# 기대: HTML 응답

# API 프록시 확인
curl -s http://localhost:3000/api/health
```

#### 5. 프로덕션 배포 테스트

```bash
# Gunicorn으로 실행
gunicorn -w 4 -b 0.0.0.0:5001 flask_app:app --timeout 120

# 부하 테스트 (기본)
for i in {1..10}; do curl -s http://localhost:5001/api/health > /dev/null && echo "OK $i"; done
```

### 의존성
- Phase 0~6 모두 완료

### 예상 산출물
- 전체 시스템 동작 확인 보고서
- `.gitignore`
- 배포 설정 파일 (Railway/Docker)
- 수동 테스트 스크립트

---

## 파일 목록 총괄표

### 백엔드 (Python)

| #   | 파일                                        | Phase | 추정 줄수 | 스펙 여부     |
| --- | ----------------------------------------- | ----- | ----- | --------- |
| 1   | `flask_app.py`                            | 4     | ~30   | **설계 필요** |
| 2   | `config.py`                               | 1     | ~250  | **설계 필요** |
| 3   | `models.py`                               | 1     | ~600  | **설계 필요** |
| 4   | `run.py`                                  | 4     | ~300  | **설계 필요** |
| 5   | `market_gate.py`                          | 4     | ~300  | **설계 필요** |
| 6   | `screener.py`                             | 4     | ~400  | **설계 필요** |
| 7   | `scheduler.py`                            | 4     | ~200  | **설계 필요** |
| 8   | `signal_tracker.py`                       | 2     | ~200  | **설계 필요** |
| 9   | `all_institutional_trend_data.py`         | 2     | ~150  | **설계 필요** |
| 10  | `requirements.txt`                        | 0     | ~20   | **설계 필요** |
| 11  | `app/__init__.py`                         | 0     | ~40   | **설계 필요** |
| 12  | `app/utils/cache.py`                      | 4     | ~30   | **설계 필요** |
| 13  | `app/routes/kr_market.py`                 | 4     | ~800  | **설계 필요** |
| 14  | `app/routes/common.py`                    | 4     | ~800  | **설계 필요** |
| 15  | `engine/config.py`                        | 1     | ~200  | **설계 필요** |
| 16  | `engine/models.py`                        | 1     | ~200  | **설계 필요** |
| 17  | `engine/collectors.py`                    | 2     | ~400  | **설계 필요** |
| 18  | `engine/scorer.py`                        | 3     | ~250  | **설계 필요** |
| 19  | `engine/position_sizer.py`                | 3     | ~100  | **설계 필요** |
| 20  | `engine/llm_analyzer.py`                  | 3     | ~150  | **설계 필요** |
| 21  | `engine/generator.py`                     | 3     | ~500  | **설계 필요** |
| 22  | `chatbot/core.py`                         | 5     | ~500  | **설계 필요** |
| 23  | `chatbot/prompts.py`                      | 5     | ~200  | **설계 필요** |
| 24  | `chatbot/memory.py`                       | 5     | ~100  | **설계 필요** |
| 25  | `chatbot/history.py`                      | 5     | ~80   | **설계 필요** |
| 26  | `chatbot/data_loader.py`                  | 5     | ~120  | **설계 필요** |
| 27  | `chatbot/__init__.py`                     | 0     | ~20   | **설계 필요** |
| 28  | `scripts/create_kr_stock_list.py`         | 2     | ~80   | **설계 필요** |
| 29  | `scripts/create_complete_daily_prices.py` | 2     | ~120  | **설계 필요** |

### 프론트엔드 (TypeScript/React)

| #   | 파일                                                   | Phase | 추정 줄수 | 스펙 여부     |
| --- | ---------------------------------------------------- | ----- | ----- | --------- |
| 30  | `frontend/src/lib/api.ts`                            | 6     | ~120  | **설계 필요** |
| 31  | `frontend/src/app/globals.css`                       | 6     | ~150  | **설계 필요** |
| 32  | `frontend/src/app/layout.tsx`                        | 6     | ~30   | **설계 필요** |
| 33  | `frontend/src/app/dashboard/layout.tsx`              | 6     | ~100  | **설계 필요** |
| 34  | `frontend/src/app/dashboard/kr/page.tsx`             | 6     | ~300  | **설계 필요** |
| 35  | `frontend/src/app/dashboard/kr/vcp/page.tsx`         | 6     | ~1000 | **설계 필요** |
| 36  | `frontend/src/app/dashboard/kr/closing-bet/page.tsx` | 6     | ~800  | **설계 필요** |
| 37  | `frontend/next.config.js`                            | 6     | ~15   | **설계 필요** |
| 38  | `frontend/package.json`                              | 0     | ~30   | **설계 필요** |
| 39  | `frontend/tailwind.config.ts`                        | 0     | ~20   | **설계 필요** |
| 40  | `frontend/tsconfig.json`                             | 0     | ~25   | **설계 필요** |

**총계**: ~40개 파일, 약 8,000줄

---

