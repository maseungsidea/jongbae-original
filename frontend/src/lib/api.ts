/**
 * Flask API 클라이언트 & TypeScript 타입 정의 (src/lib/api.ts)
 *
 * 설계 의도:
 * - 모든 API 호출을 이 파일로 중앙 집중화하여 엔드포인트 관리 용이
 * - Generic fetchAPI<T>로 타입 안전성 보장
 * - next.config.ts의 rewrites 덕분에 /api/* 는 Flask(5001)로 자동 프록시
 */

// ────────────────────────────────────
// 공통 타입
// ────────────────────────────────────

export interface ScoreDetail {
    news: number;
    volume: number;
    chart: number;
    candle: number;
    consolidation: number;
    supply: number;
    total: number;
    llm_reason?: string;
}

export interface ChecklistDetail {
    has_news: boolean;
    news_sources: string[];
    is_new_high: boolean;
    is_breakout: boolean;
    supply_positive: boolean;
    volume_surge: boolean;
}

export interface NewsItem {
    title: string;
    source: string;
    url: string;
}

// ────────────────────────────────────
// 종가베팅 V2 시그널 (engine/generator.py Output)
// ────────────────────────────────────

export interface ClosingBetSignal {
    stock_code: string;
    stock_name: string;
    market: "KOSPI" | "KOSDAQ";
    sector: string;
    signal_date: string;
    signal_time: string;
    grade: "S" | "A" | "B" | "C";
    score: ScoreDetail;
    checklist: ChecklistDetail;
    news_items: NewsItem[];
    current_price: number;
    entry_price: number;
    stop_price: number;
    target_price: number;
    r_value: number;
    position_size: number;
    quantity: number;
    r_multiplier: number;
    trading_value: number;
    change_pct: number;
    status: "pending" | "entered" | "exited";
    created_at: string;
}

export interface ClosingBetResult {
    date: string;
    total_candidates: number;
    filtered_count: number;
    signals: ClosingBetSignal[];
    by_grade: Record<string, number>;
    by_market: Record<string, number>;
    processing_time_ms: number;
}

// ────────────────────────────────────
// VCP / KR 마켓 시그널
// ────────────────────────────────────

export interface VCPSignal {
    ticker: string;
    name: string;
    market: string;
    score: number;
    change_pct: number;
    volume_ratio: number;
    foreign_net: number;
    inst_net: number;
    entry_price: number;
    stop_price: number;
    target_price: number;
    updated_at: string;
}

// ────────────────────────────────────
// Market Gate
// ────────────────────────────────────

export interface SectorResult {
    name: string;
    signal: "bullish" | "bearish" | "neutral";
    change_1d: number;
    score: number;
}

export interface MarketGateResult {
    gate: "GREEN" | "YELLOW" | "RED";
    score: number;
    reasons: string[];
    sectors: SectorResult[];
    metrics: Record<string, number>;
    updated_at?: string;
}

// ────────────────────────────────────
// AI 분석
// ────────────────────────────────────

export interface AIAnalysis {
    ticker: string;
    name: string;
    grade: string;
    score: ScoreDetail;
    analysis_date: string;
    summary?: string;
}

// ────────────────────────────────────
// 기본 fetch 래퍼
// ────────────────────────────────────

async function fetchAPI<T>(
    endpoint: string,
    options?: RequestInit
): Promise<T> {
    const res = await fetch(`/api${endpoint}`, {
        headers: { "Content-Type": "application/json" },
        ...options,
    });

    if (!res.ok) {
        const text = await res.text().catch(() => "");
        throw new Error(`API 오류 [${res.status}]: ${endpoint} - ${text}`);
    }

    return res.json() as Promise<T>;
}

// ────────────────────────────────────
// 종가베팅 V2 API
// ────────────────────────────────────

export const closingBetAPI = {
    /** 최신 종가베팅 V2 시그널 조회 */
    getLatest: () =>
        fetchAPI<ClosingBetResult>("/kr/jongga-v2/latest"),

    /** 저장된 분석 날짜 목록 */
    getHistoryDates: () =>
        fetchAPI<string[]>("/kr/jongga-v2/dates"),

    /** 특정 날짜 히스토리 */
    getHistory: (date: string) =>
        fetchAPI<ClosingBetResult>(`/kr/jongga-v2/history/${date}`),

    /** 전체 엔진 실행 (시간 소요) */
    run: (capital?: number) =>
        fetchAPI<ClosingBetResult>("/kr/jongga-v2/run", {
            method: "POST",
            body: JSON.stringify({ capital: capital ?? 50_000_000 }),
        }),
};

// ────────────────────────────────────
// KR 마켓 API
// ────────────────────────────────────

export const krAPI = {
    /** Market Gate 상태 */
    getMarketGate: () =>
        fetchAPI<MarketGateResult>("/kr/market-gate"),

    /** VCP 시그널 목록 */
    getSignals: () =>
        fetchAPI<{ signals: VCPSignal[]; count: number }>("/kr/signals"),

    /** AI 분석 전체 */
    getAIAnalysis: () =>
        fetchAPI<AIAnalysis[]>("/kr/ai-analysis"),

    /** AI 히스토리 날짜 목록 */
    getAIHistoryDates: () =>
        fetchAPI<string[]>("/kr/ai-history-dates"),

    /** 특정 날짜 AI 히스토리 */
    getAIHistory: (date: string) =>
        fetchAPI<AIAnalysis[]>(`/kr/ai-history/${date}`),

    /** 종목 차트 데이터 */
    getStockChart: (ticker: string) =>
        fetchAPI<unknown>(`/kr/stock-chart/${ticker}`),

    /** 시장 상태 (MA200 기반) */
    getMarketStatus: () =>
        fetchAPI<unknown>("/kr/market-status"),

    /** 성과 요약 */
    getPerformance: () =>
        fetchAPI<unknown>("/kr/performance"),
};

// ────────────────────────────────────
// 챗봇 API
// ────────────────────────────────────

export const chatbotAPI = {
    /** AI 챗봇에 메시지 전송 */
    send: (message: string, sessionId: string = "default") =>
        fetchAPI<{ response: string; session_id: string }>("/chatbot", {
            method: "POST",
            body: JSON.stringify({ message, session_id: sessionId }),
        }),
};

// ── OCF 오버나이트 리스크 ──────────────────────────────
export interface OCFFlag {
    name: string;
    triggered: boolean;
    value: number;
    threshold: number;
    message: string;
}

export interface OCFResult {
    date: string;
    severity: "OK" | "WARNING" | "DANGER";
    summary: string;
    flags: OCFFlag[];
}

// ── 성과 추적 ──────────────────────────────────────────
export interface PerformanceSummary {
    total: number;
    win_rate: number;
    avg_return: number;
    by_reason: Record<string, number>;
}

export interface CumulativeReturn {
    data: { exit_date: string; cumulative_pnl: number }[];
}

export interface SignalRow {
    signal_id: string;
    ticker: string;
    name: string;
    grade: string;
    signal_date: string;
    entry_price: number;
    stop_price: number;
    target_price: number;
    status: string;
    exit_date?: string;
    exit_price?: number;
    exit_reason?: string;
    return_pct?: number;
    days_held?: number;
    partial_taken?: number;
    trailing_stop?: number;
    peak_price?: number;
}

export interface SignalHistory {
    signals: SignalRow[];
    total: number;
    page: number;
    per_page: number;
}

// ── 관리자 ──────────────────────────────────────────────
export interface AdminStatus {
    jobs: Record<string, { last_run?: string; last_result?: string }>;
    ocf_latest?: OCFResult;
    data_freshness: Record<string, string>;
}

// ── 백테 파라미터 비교 ──────────────────────────────────
export interface BacktestStats {
    trades: number;
    ev_pct: number;
    wr: number;
    mdd_pct: number;
    filter_rate?: number;
    filtered_trades?: number;
}

export interface BacktestComparison {
    label: string;
    baseline: BacktestStats;
    with_ocf_warning: BacktestStats;
    with_ocf_danger_only: BacktestStats;
    ocf_flag_days: Record<string, number>;
    goal_met: Record<string, boolean>;
}

export const ocfAPI = {
    getLatest: () => fetchAPI<OCFResult>("/ocf/latest"),
};

export const performanceAPI = {
    getSummary: () => fetchAPI<PerformanceSummary>("/kr/performance"),
    getCumulativeReturn: () => fetchAPI<CumulativeReturn>("/kr/cumulative-return"),
    getSignalHistory: (page = 1, strategy = "") =>
        fetchAPI<SignalHistory>(`/kr/signals/history?page=${page}&strategy=${strategy}`),
};

export const adminAPI = {
    getStatus: () => fetchAPI<AdminStatus>("/admin/status"),
    trigger: (job: string) =>
        fetchAPI<{ success: boolean; result?: unknown }>(`/admin/trigger/${job}`, {
            method: "POST",
        }),
};

export const backtestAPI = {
    getLatest: () => fetchAPI<BacktestComparison>("/kr/backtest/latest"),
    run: (params: Record<string, number>) =>
        fetchAPI<BacktestComparison>("/kr/backtest/run", {
            method: "POST",
            body: JSON.stringify({ params }),
        }),
};

