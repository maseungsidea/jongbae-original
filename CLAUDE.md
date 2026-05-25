# 종가배팅앱(오리지널) — 개발 가이드

## 프로젝트 목표

이 앱은 **한국 주식 종가 돌파 전략(VCP 기반)**을 자동화한 페이퍼→실전 투자 시스템이다.

### 왜 건당 EV 2%가 목표인가 — 벤치마크 비교

```
전략                     │ 연 수익률
─────────────────────────┼──────────────────────────
은행 예금                │ 3.5%
코스피 ETF 장기          │ 10%
워런 버핏 (역대 최고)    │ 20%
종배앱 현재 (연환산)     │ 12.8%  ← 코스피 ETF 수준 (의미 없음)
종배앱 목표 (건당 EV 2%) │ 33.6%  ← 워런 버핏 초과, 비로소 의미 있는 수준
```

**결론**: 건당 EV +1.66% 는 코스피 ETF 와 다를 것이 없다.
**건당 EV +2% 이상이 이 앱 존재의 최소 조건**이다.
이 기준선에 미달하는 채점 파라미터로 실전 투자하는 것은 수수료+세금 손실이다.

### 핵심 성과 목표 (KPI) — 개발의 최소 기준선

| 지표 | 목표 | 현재 (sw_pe_t8 백테) |
|------|------|----------------------|
| 일 추천 종목 수 | **최소 1건 / 거래일** | 0건 (BB폭 임계 문제로 공회전 중) |
| 건당 기대 수익률 (EV) | **+2.0% 이상** | +1.66% (close) / +2.37% (next_open ✅) |
| 연환산 수익률 목표 | **33.6% 이상** | 12.8% (현재, 개선 필요) |
| 승률 (WR) | 50% 이상 | 55.9% (close) / 49.5% (next_open) |
| MDD | -30% 이하 | -53.32% (개선 필요) |

> **⚠️ 개발 원칙 — 반드시 준수**:
> 1. 건당 EV 2% 미달 파라미터로는 실전 투자 금지.
> 2. 채점 시스템 수정 → 백테 EV 2% 확인 → 페이퍼 4주 → 실전 순서를 절대 건너뛰지 않는다.
> 3. "일 최소 1건 추천"이 안 되는 상태(0건 공회전)는 시스템 결함이다. 즉시 수정 우선.
> 4. next_open 전략(EV +2.37%)이 이미 목표 달성 — 이를 기준으로 close 전략을 개선한다.

---

## 아키텍처 개요

```
Naver Finance (HTML 스크래핑)
    │  naver_top_gainers() — KOSPI/KOSDAQ 각 30개, 당일 급등 상위
    ▼
engine/generator.py  ── run_screener()
    │  12점 채점 (뉴스·거래대금·차트·캔들·변동성수축·수급)
    │  Grade S/A/B/C 결정
    ▼
signal_tracker.py
    │  전략 A: signals_log_A_close.csv     (당일 종가 진입)
    │  전략 B: signals_log_B_next_open.csv (익일 시초가 + 갭 1% 필터)
    ▼
utils/notifier.py  ── Telegram 발송 (@jongbae_original_bot)
```

**스케줄 (KST)**:
- `08:50` 데이터 업데이트
- `14:50` VCP 스캔 (휴장일 자동 스킵)
- `14:55` 전략 A/B 시그널 추적
- `15:00` 텔레그램 일일 요약 발송

---

## 알려진 결함 (개발 우선순위)

### P1 — 즉시 수정
1. **캔들형태 채점**: 14:50 실행 시 pykrx 가 당일 종가 미확정 → `charts[-1]` = 전일 캔들
2. **공휴일 스킵**: ✅ 완료 (`engine/market_utils.is_trading_day()`)

### P2 — 이번 스프린트
3. **변동성수축 임계**: BB폭 ≤ 3% → 급등주 유니버스에서 hit rate 0%. `0.10`으로 완화 후 백테 재검증 필요
4. **캔들 조건 완화**: `body_ratio ≥ 0.70` AND `upper_wick ≤ 0.10` → 너무 엄격. `0.50 / 0.20` 권장

### P3 — 다음 스프린트
5. **수급 데이터**: `supply_enabled=False` (pykrx API 차단). Naver 수급 스크래퍼(`scripts/fetch_naver_supply.py`) engine 통합 후 활성화

---

## 백테스트 기준 설정 (sw_pe_t8 / sw_nopen_gap1)

```python
# engine/config.py 핵심 파라미터
atr_period = 14
atr_multiplier = 1.5
max_hold_days = 5          # 5영업일 time-exit
partial_exit_enabled = True
partial_exit_target_pct = 8.0  # +8% 시 50% 익절
entry_timing = "close"     # 전략 A
# entry_timing = "next_open", max_gap_pct = 1.0  # 전략 B
```

**Sharpe 계산 주의**: 5일 보유 기준 `√(252/5) ≈ 7.1` 로 연환산. `√252` 사용 시 2.24× 과대계상.

---

## 환경 변수

| 변수 | 설명 | 필수 |
|------|------|------|
| `TELEGRAM_TOKEN` | @jongbae_original_bot 토큰 | ✅ |
| `TELEGRAM_CHAT_ID` | 수신 chat_id | ✅ |
| `GEMINI_API_KEY` | 뉴스 LLM 분석 | 선택 |
| `JONGGA_NOTIFY` | `0` 이면 텔레그램 비활성 | - |
| `JONGGA_DATA_SOURCE` | `naver` (기본) / `pykrx` | - |
| `TZ` | `Asia/Seoul` (Railway 배포 필수) | Railway |

---

## 커맨드

```bash
python3 scheduler.py --now     # 즉시 1회 전체 실행
python3 scheduler.py           # 데몬 모드 (KST 스케줄)
python3 -m pytest tests/ -q    # 단위 테스트
python3 scripts/analyze_backtest.py --sort sharpe  # 백테 결과 비교
```
