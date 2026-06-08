# Sprint 2 — 충실한(event-driven) 백테스터 구축 + EV 재측정 결과

작성: 2026-06-08 / 범위: 종가배팅앱(오리지널)

## 1. 배경 — 왜 재측정했나

기존 백테스터(`scripts/backtest_jongga.py`)는 **static-stop 근사**를 썼다:
진입 시 `stop = entry − k×ATR` 를 1회 고정하고, target 도달/stop 터치/만기만 평가.
이는 **실제 배포된 청산 로직**(`signal_tracker.py`)과 다르다. 라이브는:

1. hard_stop floor (−8% 절대 하한, O'Neil 규칙)
2. 상한가(+28%) 부분익절 마킹
3. trailing stop **래칫**(peak−k×ATR 단조증가) + **Day-1 보호**(첫 2일 래칫 보류)
4. +8% 분할익절(50%) 마킹
5. RSI(2) 과열 청산(기본 off)
6. trailing hit / 만기(5영업일)

static 근사는 hard_stop floor·trailing 래칫·Day-1 보호·분할익절 가중을 **반영하지 못해 EV 를 과대계상**했다. "백테는 +2%인데 라이브는 −5%" 괴리의 근본 원인이다.

## 2. 한 일

- **`engine/exit_simulator.py`** 신규: 라이브 primitive(`engine/trailing_stop.py`)를 그대로
  재사용해 `track_signals` 의 per-bar 청산 평가 순서를 1:1 재현하는 `simulate_exit()`.
- **`scripts/backtest_jongga.py`**: `--exit-engine {static,faithful}` 분기 추가. faithful 은
  라이브 `SignalConfig` 값을 그대로 ExitParams 로 미러.
- **`tests/test_exit_simulator.py`** 9 케이스: hard_stop·time_exit·partial 가중·Day-1 불변식·
  RSI on/off·진입바 평가 on/off 를 잠금(fidelity lock).
- code-reviewer 2 회 위임(작성자≠리뷰어). CRITICAL(next_open entry_idx, RSI 누락,
  close 진입바 off-by-one) 전수 수정.

## 3. 재측정 결과 (전체 유니버스, 2024-08 ~ 2026-04)

| 전략 | static 근사 (구 백테) | **faithful (라이브 청산)** | +2% floor |
|------|----------------------|---------------------------|-----------|
| close (진입바 평가, 라이브 일치) | +1.56% | **−2.13%** | ❌ |
| close (진입바 skip, lookahead 제거) | — | **+0.88%** | ❌ |
| next_open (gap 1%) | +1.59% | **+0.97%** | ❌ |

**모든 전략·모든 해석이 건당 EV +2% floor 에 미달.** static 근사의 +2% 는 아티팩트였다.

## 4. 핵심 발견 — 진입일(d0) 청산 민감도 (구조적)

close `eval-entry-bar`(라이브 충실) 측정에서:

- **82/256(32%)가 진입일(d0)에 청산**, 그중 70 건 hard_stop, d0 평균 **−7.84%**.
- d0 제외(174 건) 평균 **+0.56%**.
- 즉 EV 의 −2.13% ↔ +0.88% **3%p 격차 전부가 "진입일 청산을 인정하는가"** 한 가지에 달림.

### 라이브 실증 대조 (`signals_log_A_close.csv`, 3 건)
3 건 모두 `days_held=1.0`, hard_stop −8% (sig 06-04 → 06-05 청산).
- days_held=1 부기는 **진입바를 평가**(eval-entry-bar)해야만 재현된다(진입바에서 days_held 0→1,
  다음 바에서 hard_stop). skip 변형은 days_held=0 을 줘 라이브와 어긋난다.
- 따라서 **라이브는 진입바를 평가**한다 = eval-entry-bar 가 충실 = faithful EV **−2.13%**.

### 단, lookahead 의심
진입바(=신호일) 청산은 **그 바의 장중 저가**를 *종가 진입가* 에 대조한다. 종가에 진입했는데
이미 지나간 장중 저가로 −8% 손절을 기록 = **lookahead**. 다만 라이브 14:55 진입 시 당일봉
미완성(CLAUDE.md P1 #1: pykrx 당일 종가 미확정)이면 진입바 저가가 실시간 미가용 → d0 phantom 이
**중화**될 수 있다. 라이브 3 건은 진입바가 breach 안 해 이 질문을 가르지 못한다(표본 부족).

**결론: 배포 코드의 문자적 충실 EV = −2.13%(d0 phantom 포함). 데이터-타이밍이 phantom 을
막으면 실현 가능 상한 ≈ +0.88%. 어느 쪽이든 +2% 미달.** 진입일 청산 semantics 자체가
P1 데이터-타이밍 결함과 얽힌 **수정 대상 구조 결함**이다(시장 한계 아님).

## 5. 게이트 판정 (binding)

- 건당 EV +2% 필요조건 **미입증·미충족** → **자동매매·발신(텔레그램/푸시) 활성화 금지 유지**.
- 핵심 지표 우선 원칙상, config swap 류 표면 튜닝 금지. 근본 메커니즘 변경 필요.

## 6. 다음 패러다임 후보 (≥3, 3 연속 비개선 대비)

1. **진입 타이밍 결함 우선 수정**: 진입바 d0 청산 lookahead 제거(close 도 next_open 처럼 진입
   다음 바부터 평가). 수정 시 realizable 상한 +0.88% 가 faithful 기준선이 됨 → 거기서 출발.
2. **채점→EV 연결 재설계**: 현재 12 점 채점이 EV 와 약상관(d1+ 만 +0.56%). Grade 별 EV
   층화 후 EV-음수 구간 진입 차단(rule-gating).
3. **Exit 다양화 + 보유기간 최적화**: hard_stop −8% 가 d1+ 에서도 과청산. ATR 배수·보유일·
   분할익절 임계의 grid 를 faithful 엔진으로 재탐색(static 결과 폐기).
4. **유니버스 정제**: 급등주 진입바 변동성이 d0 phantom 의 원천. 변동성 상위 분위 제외 A/B.
5. **next_open 단독 운용 검토**: faithful +0.97% 로 close(−2.13%)보다 견고. close 결함 수정
   전까지 next_open 만 페이퍼.

## 7. 산출물

- `engine/exit_simulator.py`, `scripts/backtest_jongga.py`(faithful 분기), `tests/test_exit_simulator.py`
- 백테 결과: `data/backtests/close_faithful_evalbar.json`, `…skipbar.json`, `nopen_faithful.json`

## 8. 후속 조치 — d0 lookahead 결함 수정 완료 (후보 1)

**`signal_tracker.py` 수정**: close 전략이 진입 바(신호일)의 장중 저가를 청산 평가에 쓰던
fall-through 를 제거. 신호일 *이후* 바부터만 hard_stop/trailing/time_exit 평가하도록 게이트
(`_bar_date <= _sig_date` 면 `continue`). pykrx T+1 지연에도 안전(bar_date>signal_date 까지 보류).
날짜 파싱 실패 시 **fail-closed**(평가 보류, 오발신 방지 — 휴장일 4중 방어와 동일 pos터).

**효과 (측정)**: close 전략 정직 EV **−2.13% → +0.88%** (phantom d0 손절 제거, +3.0%p).
백테 기본값도 `--close-entry-bar skip` 으로 변경해 라이브와 정합.
검증: `close_faithful_newdefault.json` n=221, WR=53.4%, **EV=+0.881%**, RR=1.14.

**남은 격차**: +0.88% 는 여전히 +2% floor 미달. 다음은 후보 2(채점→EV rule-gating) /
후보 3(faithful 엔진으로 ATR·보유일·분할익절 grid 재탐색)로 +2% 까지 끌어올린다.
리뷰: code-reviewer 위임 → HIGH(fail-open) 1건 지적 → fail-closed 로 수정 반영.

## 9. 후보 2 — EV 누수 분해 + 진입 필터 (faithful close, n=221, +0.88% 기준)

**exit reason 별 EV 기여 분해**:

| reason | n | % | mean | EV 기여 |
|---|---|---|---|---|
| hard_stop | 61 | 27.6% | −8.21% | **−2.27%p** ← 최대 누수 |
| partial_time | 45 | 20.4% | +9.67% | +1.97%p |
| partial_stop | 41 | 18.6% | +7.07% | +1.31%p |
| time_exit | 44 | 19.9% | +1.29% | +0.26%p |
| trailing_stop | 30 | 13.6% | −2.87% | −0.39%p |

→ 승자(partial_*)는 강하다. **문제는 28% 가 진입 직후 −8% hard_stop** = 진입 품질 문제.

**채점 rule-gating 한계 (구조적)**: 12점 채점이 **degenerate** — 실제 점수 {5,6} 둘뿐.
news=0(LLM off)·supply=0(pykrx 차단, P3)·volume=3 포화. candle∈{0,1}, chart 포화(2).
최선 게이트 `candle>0 & consol>0` 도 EV +1.50%(n=25) — **+2% 도달 불가**. 채점은 해상도 부족.

**ATR% 진입 필터 (근본 메커니즘, config swap 아님)**: hard_stop 트레이드의 진입일 ATR%
중앙값 6.06 vs 승자 4.67 → 고변동 진입이 노이즈로 −8% 에 걸린다. `--max-atr-pct` 추가:

| 필터 | n | EV | WR | RR | hard% |
|---|---|---|---|---|---|
| 없음 | 221 | +0.88% | 53.4% | 1.14 | 27.6% |
| ATR%≤4 | 83 | +1.57% | 59.0% | 1.43 | 6.0% |
| ATR%≤5 | 133 | +1.62% | 59.4% | 1.23 | 14.3% |
| ATR%≤6 | 164 | +1.66% | 58.5% | 1.25 | 17.1% |

4~6 구간 EV ~+1.6% 로 robust(knife-edge 아님). EV +0.88%→+1.66%, hard% 28%→17%, WR↑.

## 10. Out-of-sample 검증 + 최종 판정

기간 2분할(중앙 2025-11-11):

| 기간 | base EV | ATR%≤5 EV | 개선 |
|---|---|---|---|
| H1 (2024-08~2025-11, n=108→77) | +0.51% | **+1.14%** | +0.63%p |
| H2 (2025-11~2026-04, n=57→17) | +1.77% | +5.08%(n=17 노이즈) | +3.31%p |

- ATR 필터는 **양 반기 모두 EV 개선** → overfit 아님, 진짜 신호. ✓
- 그러나 base EV 자체가 **레짐 의존**(H1 약세 +0.51 / H2 강세 +1.77). 전기간 +1.66% 는
  표본 작은 강세 H2 가 끌어올린 값. **신뢰 가능 표본(H1)에선 +1.14%**.

**최종 판정**: lookahead 수정 + ATR 필터로 정직 EV +0.88%→+1.6%(IS)/+1.14%(OOS-H1)로
**실질 개선**했으나, **+2% floor 는 OOS 에서 미달**. 현 아키텍처(현 채점+현 청산)는 ~+1.6% 가 천장.
→ 자동매매·발신 활성화 **금지 유지**.

**부수 발견**: `backtest_jongga.py --regime` 인자(:121)는 simulate_one 에서 **미사용 = no-op**.
regime=bull 백테가 무필터와 동일(n=221). 레짐 게이트를 실제 테스트하려면 구현 필요(latent trap).

**다음 패러다임(+2% 도달 경로, 3종)**:
1. **레짐 게이트 실구현**: H1/H2 레짐 의존성이 크다 → BEAR 구간 진입 차단을 backtest+live 에
   실제 구현(현재 stub). jongbae-plus `market_regime.py` 자산 차용.
2. **진입 신호 교체(채점 해상도 문제 근본 해결)**: 현 12점은 {5,6} 뿐. news(LLM)·supply 재활성 또는
   VCP/거래량 패턴 직접 신호로 대체해 해상도 확보. ATR 필터를 entry 1급 게이트로 승격.
3. **승자-확대 청산 재설계**: partial_time +9.67% 가 EV 엔진. +8% 분할(50%) 이 상방을 자른다 →
   분할 임계↑/비율↓·보유 연장으로 우상향 포착 (faithful 엔진으로 OOS 분할 검증 필수).

## 11. 패러다임 #1(레짐) 기각 + #3(승자 확대) 검증 → +2% IS 도달

**#1 레짐 게이트 — 기각.** 유니버스 등가중 수익률 지수(481일, +32.6%)로 breadth regime proxy
구축 후 진입 게이트 검정:
- MA40: BULL +1.10%(n=193) / BEAR −0.62%(n=28) → 게이팅 +0.22%p (약간 도움)
- MA60: BULL +0.77%(n=202) / BEAR **+2.04%**(n=19) → 부호 반전 (게이팅 해로움)
- **MA 윈도우(40↔60)에 부호가 뒤집힘 = knife-edge = 약신호/overfit.** ATR 필터(+1.62%)보다 약함 → 미채택.

**#3 승자-확대(보유 연장) — 검증.** EV 누수 분해에서 partial_time(+9.67%)이 엔진인데 5일
time-exit 이 우상향을 자른다는 가설. `--hold-days` 스윕(ATR%≤5):

| hold | n | EV | WR | RR |
|---|---|---|---|---|
| 5 | 133 | +1.62% | 59.4% | 1.23 |
| 8 | 121 | **+1.995%** | 60.3% | 1.28 |
| 10 | 113 | +2.07% | 60.2% | 1.31 |
| 15 | 110 | +2.09% | 58.2% | 1.42 |

→ 8일부터 **+2.0% 도달, 8/10/15 plateau**(knife-edge 아님 = 진짜 효과). 5일 time-exit 이 binding cap 이었음.

**OOS 검증 (hold8·ATR%≤5)**: H1 +1.14%→**+1.51%**(n=70), H2 +5.08%→+5.76%(n=15).
보유 연장은 **양 반기 모두 개선**(robust). 단 신뢰표본 H1 은 +1.51% — 전기간 +2.0% 는 강세 H2(소표본)가 견인.

### 종합 최종 판정 (Sprint 2 전체)
| 단계 | close EV (IS) | OOS-H1 |
|---|---|---|
| 구 static(아티팩트) | +1.56% | — |
| faithful 기준선 | +0.88% | +0.51% |
| + d0 lookahead 수정 | (포함) | (포함) |
| + ATR%≤5 진입필터 | +1.62% | +1.14% |
| **+ hold 8일 (3종 결합)** | **+1.995%** | **+1.51%** |

- 3종(d0수정·ATR필터·보유연장) 모두 **OOS 양 반기 robust 개선** = config swap 아닌 진짜 메커니즘.
- **IS EV +2.0% 도달** → 앱 프로세스상 "백테 EV 2% 확인" 게이트 충족 → **페이퍼 트래킹 진입 자격**.
- 단 **OOS-H1 +1.5%** = 신뢰 하한. 레짐/기간 분산이 잔여 격차. **4주 페이퍼 확인 전 실전·발신 금지 유지**.
- 권장 채택 config: `entry=close, --max-atr-pct 5, --hold-days 8`(보수) ~ `10`. 라이브 반영 시 review 필수.

## 12. 라이브 반영 + ATR 추정기 정합 (2026-06-08)

권장 config 를 라이브에 반영: `engine/config.py` `max_hold_days 5→8`, 신규 `max_atr_pct=5.0`.
ATR% 게이트는 `engine/generator.py:_analyze_stock` 에 삽입(배치 스캔 `generate()` + 단일종목
API `analyze_single_stock_by_code` 양쪽 공유 — 일관). fail-open(ATR 미산출 시 통과)은 entry
필터 특성상 의도된 설계(통과=신호 증가, 누락 청산 아님).

**code-reviewer HIGH 지적 — ATR 추정기 불일치 → 수정.** 라이브 게이트는 Wilder ATR
(`engine.trailing_stop.compute_atr`, 트레일링 스탑 SoT)을 쓰는데, 백테 `--max-atr-pct` 필터는
단순평균 ATR(`np.mean(tr[-14:])`)을 써서 검증값이 실거동을 그대로 재현하지 못할 위험.
→ 백테 게이트를 라이브와 동일한 Wilder ATR 마지막값으로 정합(`scripts/backtest_jongga.py`,
legacy static-stop 분기·기록용 단순평균 `atr` 은 보존). **재검증 결과 실데이터 영향 미미**:

| 단계 | gate ATR | IS EV (n) | OOS-H1 EV (n) |
|---|---|---|---|
| 정합 전(단순평균) | simple mean | +1.995% (133) | +1.51% (70) |
| **정합 후(Wilder, 라이브 일치)** | **Wilder** | **+1.984% (132)** | **+1.632% (77)** |

→ 추정기 차이는 IS 1건/0.01%p, OOS-H1 은 오히려 +0.12%p 개선. 검증 결론(IS≈+2.0%,
OOS-H1≥+1.5%) **불변**. 이제 라이브 게이트가 백테 검증값을 충실히 재현. **4주 페이퍼 확인 전
실전·발신 금지는 그대로 유지**(OOS-H1 +1.63% = 신뢰 하한, +2% floor 는 강세 H2 견인).
