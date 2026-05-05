# 종가베팅 백테스트 + 가설 sweep 결과 (Phase 1)

기준일: 2026-05-05
데이터: KOSPI+KOSDAQ 전 종목 × 730일 OHLCV (1,289,951행)
백테 엔진: `scripts/backtest_jongga.py` (engine/scorer.py 12점 채점 재사용)

---

## ⚠ 백테스트 가정 / 한계

- **뉴스 / LLM 점수 = 0** (과거 뉴스 수집 불가, 정보 누수 방지)
- **수급(외인·기관) 점수 = 0** (pykrx · FDR 모두 historical 일별 net buy 미제공)
  → 12점 만점 중 **7점이 cap**. 운영(12점) 등가 검증 시 별도 데이터 소스 필요
- **수수료** 0.21% round-trip (한국 시장)
- **Sequential overlap**: 한 종목 in_position 동안 신규 진입 차단

따라서 본 백테는 **"뉴스·수급 미반영, 차트 + 거래대금 + 캔들 + 횡보만으로 진입할 때의 EV 하한선"**으로 해석.

---

## 1. Baseline 결과

설정: cutoff=5, hold=5d, entry=close, trailing=atr15(1.5×ATR), target=fixed5(+5%), 거래대금≥100억

```
n=208 trades / WR 64.9% / EV +0.494% / RR 0.65
청산 사유: target 60% / stop 26% / time 13%
```

→ **양수 EV 확보**. 사용자가 우려한 "0건 / 마이너스 EV"는 vcp-scan top_n=10 한계 때문이고, 전 종목 풀 백테는 자동매매 가능 수준.

다만 **RR 0.65** (avg_loss > avg_win)는 약점 — 익절 +5%가 winner를 자르고 있다.

---

## 2. Sweep #1 결과 (11개 변형, EV 내림차순)

| # | 변형 | n | WR | EV | RR | reasons |
|---|------|---|-----|----|----|---------|
| 9 | **target off + atr15 trailing** | 152 | 48.7% | **+2.070%** | **1.68** | time 101, stop 51 |
| 8 | trailing off (익절만) | 203 | 69.0% | +0.838% | 0.62 | target 127, time 76 |
| 2 | cutoff=6 + grade-pass (운영 등가) | 34 | 61.8% | +0.557% | 0.79 | target 18, stop 13, time 3 |
| 10 | atr20 (loose stop) | 207 | 67.6% | +0.540% | 0.58 | target 127, time 46, stop 34 |
| 1/11/12 | **baseline = min_tv 50억 = 500억** | 208 | 64.9% | +0.494% | 0.65 | target 125, stop 55, time 28 |
| 5 | hold 7d | 204 | 65.7% | +0.450% | 0.61 | target 128, stop 62, time 14 |
| 3 | cutoff 4 (완화) | 811 | 63.6% | +0.381% | 0.66 | target 472, stop 222, time 117 |
| 7 | fixed3 stop (-3%) | 222 | 44.6% | +0.331% | 1.48 | stop 119, target 94, time 9 |
| 4 | hold 3d | 220 | 59.6% | +0.185% | 0.73 | target 106, time 71, stop 43 |
| 6 | **entry next_open** | 185 | 60.0% | **-0.235%** | 0.61 | target 100, stop 62, time 23 |

---

## 3. 핵심 인사이트

### 3-1. **+5% 익절이 winner를 자른다 — 가장 큰 발견**
- target=off + atr15 trailing → EV **4배 (+0.494% → +2.07%)**, RR도 0.65 → 1.68로 정상화
- 종가베팅 신호가 잡은 종목은 +5% 이상 추세가 자주 이어짐
- 운영의 익절 룰을 **+8% / +10% / 또는 trailing-only로 변경** 권장

### 3-2. **Entry next_open은 EV 음수 (-0.235%)**
- 종가→익일 시초 갭에서 알파 소실
- 즉 **"종가 직전 진입"이 핵심 알파 원천**, 익일로 미루면 무너짐
- 운영 환경에서 정확한 종가 진입이 어렵다면, 갭 필터 (+2% 이상 skip) 같은 보호 필요

### 3-3. **min_trading_value 무관 (50/100/500억 동일)**
- score volume 항목이 1천억 깔고 있어 min_tv는 효과 없음
- 거래대금 필터는 **score 가중치로만 작동** — 별도 cutoff 의미 없음

### 3-4. **운영 등가 (cutoff=6 + grade)는 거래수 부족**
- 2년에 34건 = 월 1.4건. 자동매매로는 부족
- 단, EV는 +0.557%로 양수 (n=34 통계적 검정력 약함)

### 3-5. **fixed3 손절은 RR 1.48로 좋지만 WR 44.6%로 추락**
- 너무 빠른 손절은 stop=119건으로 손절률 53.6% → 심리 부담 큼
- ATR 기반 1.5×~2.0× trailing이 더 자연스러움

---

## 4. 자동매매 권장 설정 후보

| 후보 | 설정 | 거래수 | 특징 |
|------|------|--------|------|
| **A. 고EV** | target=off + atr15 trailing, hold=5d | 152/2y (월 6건) | EV +2.07%, RR 1.68. WR 48.7%로 심리 부담 |
| **B. 안정** | trailing off + target +5%, hold=5d | 203/2y (월 8건) | EV +0.838%, WR 69%. RR 0.62 — 큰 손실 위험 |
| **C. 균형** | target=fixed8 + atr15 trailing | sweep 中 | (Sweep #2에서 검증) |

---

## 5. Sweep #2 결과 (8개 확장 변형)

| # | 변형 | n | WR | EV | RR |
|---|------|---|-----|----|----|
| ⭐ 19 | **hold=10d + target=off + atr15** | 126 | 41.3% | **+2.566%** | **2.18** |
| ⭐ 15 | **target=off + atr10 (tight)** | 154 | 42.9% | +2.247% | 2.31 |
| 16 | target=off + atr20 (loose) | 151 | 50.3% | +1.964% | 1.49 |
| ⭐ 17 | **cutoff=4 + target=off + atr15** | **611** | 47.9% | **+1.602%** | 1.61 |
| 13 | target=fixed8 + atr15 | 190 | 57.4% | +1.037% | 1.01 |
| 14 | target=fixed10 + atr15 | 176 | 54.0% | +0.951% | 1.11 |
| 18 | cutoff=4 + target=fixed8 | 735 | 56.2% | +0.830% | 1.00 |
| 20 | cutoff=6 + grade + target=off | 28 | 46.4% | +0.320% | 1.28 |

추가 인사이트:
- **보유 5d → 10d 늘리면 EV +0.49%p** (target=off 조건). 큰 winner는 5d로 부족
- **ATR 1.0×~1.5× tight stop이 ATR 2.0×보다 EV 우위** (target=off에서)
- **cutoff 4 + target=off**: 거래수 611건 (월 25건) + EV +1.602% 유지 → **자동매매 최적해**
- target=fixed8/10은 +5%보다 명확히 좋지만 (EV 2배), target=off보다 EV 절반

---

## 6. 🎯 자동매매 추천 설정 (최종)

| 우선 | 설정 | n | WR | EV | RR | 비고 |
|------|------|---|-----|----|----|------|
| **A** | cutoff=4 + target=off + atr15 + hold=5d | 611 | 47.9% | +1.602% | 1.61 | **자동매매 1순위 — 거래수 충분, 큰 winner** |
| B | cutoff=5 + target=off + atr15 + hold=10d | 126 | 41.3% | +2.566% | 2.18 | 최고 EV, 거래 적음 (월 5건) |
| C | cutoff=5 + target=off + atr10 + hold=5d | 154 | 42.9% | +2.247% | 2.31 | 손절 빠름 + winner 끝까지 |
| D | cutoff=5 + target=fixed8 + atr15 + hold=5d | 190 | 57.4% | +1.037% | 1.01 | WR/RR 균형, 안정 |

→ **A 추천**: 거래대금 100억+ + 차트·캔들·볼린저 채점 4점+ + 종가 진입 + ATR 1.5× trailing + 익절 없음 + 5일 보유
- 월 25건 정도라 자동매매로 의미있는 빈도
- 단점: WR 47.9% (50% 미만) → 심리 부담 있지만 룰 자동 → 무관
- 단점 2: target=off라 큰 폭 하락 시 atr trailing이 늦게 잡을 위험. drawdown 시뮬 별도 필요

---

## 7. 미발굴 가설 (다음 작업)

### 6-1. 시그널 변형
- **2일 연속 cutoff 통과 종목만 진입** — 단발 신호 노이즈 제거
- **갭다운 후 회복** — 전일 -2% 이상 갭다운 + 당일 양봉 회복
- **Score 가중치 재배분** — chart(2점) ↑ 또는 candle(1점) ↑

### 6-2. 유니버스 재정의
- **MarketGate BULL 시에만 진입** — 현 backtester에 regime 미반영
- **시총 1000~5000억 중소형 한정** — 데이터에 marcap 컬럼 필요 (korean_stocks_list.csv 추가)
- **섹터 RS 강세 종목** — 최근 20일 outperform 섹터만

### 6-3. Exit 룰 정교화
- **부분 청산**: 50%는 +5%, 50%는 trailing
- **갭다운 즉시 손절** (진입 후 갭 -3% 이상이면 시초가 청산)
- **N일째 BE 미달 시 청산** (3일 후 +1% 미만이면 종가 청산)

### 6-4. 채점 시스템 보완
- **historical 외인·기관 일별 데이터 별도 수집** — pykrx/FDR 우회 (한국투자증권/네이버금융 크롤)
  → 백테 12점 cap 회복, 운영 등가 정확도 ↑

---

## 7. 산출물

- `data/daily_prices.csv` (1.29M rows)
- `data/backtests/baseline.json`
- `data/backtests/sw_*.json` (11 + 8 + 7 + 6 = 32 변형)
- `scripts/backtest_jongga.py` (재사용 가능 엔진)
- `scripts/run_jongga_sweep[1-4].sh`
- `scripts/analyze_backtest.py` (drawdown / Sharpe / streak 추가 메트릭)

---

## 8. ⚡ Phase 2 — drawdown 분석 후 자동매매 권장 변경 (2026-05-05 14:35)

`scripts/analyze_backtest.py` 로 32개 sweep 의 cum_return / max_drawdown /
Sharpe / max_losing_streak 를 추가 산출한 결과, **EV 가 좋아도 MDD 가
-65~-97% 인 전략은 자동매매 불가**라는 결론이 나옴.

### Top 5 by EV — drawdown 비교

| Rank | label | n | WR | EV | RR | **MDD** | maxLstr | 자동매매 적합 |
|------|-------|---|-----|----|----|---------|---------|--------------|
| 1 | sw_h20_off | 104 | 35.6% | +6.45% | 3.94 | **-81.14%** | 12 | ❌ |
| 2 | sw_h15_atr10_off | 116 | 31.9% | +4.41% | 4.49 | **-73.69%** | 17 | ❌ |
| 3 | sw_h15_off | 109 | 39.5% | +4.09% | 2.77 | **-83.93%** | 15 | ❌ |
| 4 | sw_h10_atr10_off | 128 | 35.9% | +3.29% | 3.37 | **-69.81%** | 12 | ❌ |
| 5 | sw_c4_h10_off | 510 | 42.8% | +2.29% | 2.07 | **-97.01%** | 16 | ❌ |

→ target=off 류는 **모두 -65% 이상의 drawdown** 발생. 직전 권장이었던
`cutoff=4 + target=off + hold=10d` 도 MDD -97% 로 자동매매 불가능.

### Top 5 by drawdown ascending (낮은 MDD 우선) — Sweep #4 반영

| label | n | WR | EV | RR | MDD | maxLstr | tpm |
|-------|---|-----|----|----|-----|---------|-----|
| **sw_nopen_gap1** | 101 | 49.5% | +2.37% | 1.76 | **-48.02%** | 7 | 5.3 |
| sw_t8 | 190 | 57.4% | +1.04% | 1.01 | -51.59% | 6 | 9.0 |
| **sw_pe_t8** | 152 | 55.9% | +1.66% | 1.26 | **-53.32%** | 6 | 7.2 |
| sw_pe_t5 | 152 | 55.9% | +1.40% | 1.23 | -55.61% | 10 | 7.2 |
| sw_nopen_gap2 | 117 | 47.9% | +2.25% | 1.83 | -57.89% | 7 | 6.2 |
| sw_pe_t10_h10 | 126 | 49.2% | +1.44% | 1.39 | -65.49% (잠정) | - | 6.0 |
| sw_c4_pe_t8_h10 | 510 | 50.2% | +1.73% | 1.53 | -84.57% | 10 | 24.3 |

### 🎯 변경된 자동매매 권장 (Phase 2 final — Sweep #1~#4 통합)

**1순위 — `sw_pe_t8` (partial_exit + atr15 + fixed8 target, hold=5d)** ⭐ 운영 채택
- 백테 WR 55.9%, EV +1.656%, RR 1.26, **MDD -53.32%**, Sharpe 2.83, maxLstr **6**
- 월 7.2건 — 월 5~10건 정도 자동매매에 무리 없음
- 50% 는 +8% 에서 익절, 50% 는 ATR(1.5×) 트레일링/5일 시간 청산
- 운영 코드 통합 완료:
  - `engine/trailing_stop.py` (신규)
  - `engine/config.py` (ATR/partial_exit 파라미터)
  - `engine/position_sizer.py` (ATR 기반 stop)
  - `engine/generator.py` (charts → ATR 자동 계산)
  - `signal_tracker.py` (partial_exit + trailing 추적)

**2순위 — `sw_nopen_gap1` (next_open + gap≤1% + target=off, hold=5d)**
- 백테 WR 49.5%, EV +2.367%, RR 1.76, MDD **-48.02%** (전 sweep 최저!)
- 월 5.3건 (낮음)
- 단점: next_open 진입 + 갭 필터 — 현재 운영 코드는 close 진입만 지원,
  추가 구현 비용 있음. 다만 안정성 면에선 가장 우월
- 후속 작업으로 검토 가치 있음 (운영 코드의 진입 시점 옵션 추가)

**3순위 — `sw_c4_pe_t8_h10` (cutoff=4 + partial_exit + fixed8 + hold=10d)**
- WR 50.2%, EV +1.730%, RR 1.53, **거래 510건 (월 24건)**, MDD -84.57%
- 거래량은 압도적이지만 -84% MDD 는 자동매매로 위험
- 자본 분할 운용(50% 만 위 전략)에는 검토 여지 있음

**비추천 — target=off + hold≥10d 전략 전반**
- EV 는 매력적이지만 -65% 이상 drawdown → 실계좌로 1년 운영 시
  최소 한 번은 자산 절반 이하로 떨어지는 시점 발생
- partial_exit 없이 long-tail 윈너에 의존 → 운영 심리/현금흐름 모두 부담

### 운영 코드 변경 요약

| 파일 | 변경 |
|------|------|
| `engine/trailing_stop.py` | (새 모듈) ATR 14 + 트레일링 stop / TrailingState |
| `engine/config.py` | atr_period/atr_multiplier/max_hold_days 추가, take_profit_pct=20 (정보용) |
| `engine/position_sizer.py` | `calculate(..., atr_value=)` 옵션 추가 |
| `engine/generator.py` | charts→ATR 자동 계산 후 sizer 전달 |
| `signal_tracker.py` | track_signals() 가 ATR 트레일링으로 청산 판단 + CSV 신규 컬럼 |
