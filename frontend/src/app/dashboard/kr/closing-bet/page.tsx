"use client";

/**
 * 종가베팅 V2 카드 그리드 페이지 (dashboard/kr/closing-bet/page.tsx)
 *
 * 설계 의도:
 * - SignalCard + ScoreBar로 12점 채점 내역을 시각화해 분석 근거 제공
 * - NaverChartWidget을 모달로 띄워 페이지 이탈 없이 차트 확인 가능
 * - 등급순 정렬로 S/A 시그널을 최상단에 배치
 */

import { useEffect, useState, useCallback } from "react";
import { closingBetAPI, type ClosingBetSignal, type ClosingBetResult } from "@/lib/api";

// ─── 등급 설정 ───
const GRADE_CONFIG = {
    S: { badge: "badge-s", glow: "card-glow-indigo", emoji: "💎" },
    A: { badge: "badge-a", glow: "card-glow-rose", emoji: "🔥" },
    B: { badge: "badge-b", glow: "card-glow-blue", emoji: "✅" },
    C: { badge: "badge-c", glow: "", emoji: "⬜" },
};

// ─── ScoreBar: 6개 항목별 점수 막대 ───
function ScoreBar({
    label,
    score,
    max,
}: {
    label: string;
    score: number;
    max: number;
}) {
    const pct = max > 0 ? (score / max) * 100 : 0;
    return (
        <div className="flex items-center gap-2">
            <span className="text-xs w-16 shrink-0" style={{ color: "var(--text-muted)" }}>
                {label}
            </span>
            <div
                className="flex-1 rounded-full h-1.5"
                style={{ background: "rgba(255,255,255,0.06)" }}
            >
                <div
                    className="h-1.5 rounded-full transition-all duration-500"
                    style={{
                        width: `${pct}%`,
                        background: pct >= 80
                            ? "var(--color-up)"
                            : pct >= 50
                                ? "var(--gate-yellow)"
                                : "#636366",
                    }}
                />
            </div>
            <span className="text-xs w-6 text-right text-white tabular-nums">{score}</span>
        </div>
    );
}

// ─── ChartModal: 네이버 차트 임베드 ───
function ChartModal({
    symbol,
    name,
    onClose,
}: {
    symbol: string;
    name: string;
    onClose: () => void;
}) {
    // 모달 외부 클릭 닫힘
    const handleBackdrop = (e: React.MouseEvent<HTMLDivElement>) => {
        if (e.target === e.currentTarget) onClose();
    };

    return (
        <div
            className="fixed inset-0 z-50 flex items-center justify-center p-4"
            style={{ background: "rgba(0,0,0,0.8)" }}
            onClick={handleBackdrop}
        >
            <div className="card w-full max-w-2xl" style={{ background: "var(--bg-surface)" }}>
                {/* 모달 헤더 */}
                <div
                    className="flex items-center justify-between px-5 py-4 border-b"
                    style={{ borderColor: "var(--border-subtle)" }}
                >
                    <p className="font-semibold text-white">
                        {name} <span style={{ color: "var(--text-muted)" }}>({symbol})</span>
                    </p>
                    <button
                        onClick={onClose}
                        className="text-xl leading-none transition-colors"
                        style={{ color: "var(--text-muted)" }}
                    >
                        ✕
                    </button>
                </div>

                {/* 네이버 차트 임베드 */}
                <div className="p-4">
                    <iframe
                        src={`https://finance.naver.com/item/fchart.naver?code=${symbol}`}
                        width="100%"
                        height="400"
                        style={{ border: "none", borderRadius: "8px" }}
                        title={`${name} 차트`}
                    />
                    <div className="mt-3 flex gap-2">
                        <a
                            href={`https://finance.naver.com/item/main.naver?code=${symbol}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-xs px-3 py-1.5 rounded-md transition-colors"
                            style={{
                                background: "rgba(255,255,255,0.06)",
                                color: "var(--text-secondary)",
                            }}
                        >
                            네이버 종목 페이지 →
                        </a>
                    </div>
                </div>
            </div>
        </div>
    );
}

// ─── StatBox: KPI 카드 내부 통계 박스 ───
function StatBox({
    label,
    value,
    highlight,
}: {
    label: string;
    value: string | number;
    highlight?: boolean;
}) {
    return (
        <div>
            <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                {label}
            </p>
            <p
                className="text-base font-bold mt-0.5 tabular-nums"
                style={{ color: highlight ? "var(--color-up)" : "var(--text-primary)" }}
            >
                {value}
            </p>
        </div>
    );
}

// ─── SignalCard: 종목 시그널 카드 ───
function SignalCard({
    signal,
    index,
    onOpenChart,
}: {
    signal: ClosingBetSignal;
    index: number;
    onOpenChart: (code: string, name: string) => void;
}) {
    const cfg = GRADE_CONFIG[signal.grade] ?? GRADE_CONFIG.C;
    const isUp = signal.change_pct > 0;

    const SCORE_ITEMS = [
        { label: "뉴스", score: signal.score.news, max: 3 },
        { label: "거래대금", score: signal.score.volume, max: 3 },
        { label: "차트", score: signal.score.chart, max: 2 },
        { label: "캔들", score: signal.score.candle, max: 1 },
        { label: "조정", score: signal.score.consolidation, max: 1 },
        { label: "수급", score: signal.score.supply, max: 2 },
    ];

    return (
        <div
            className={`card p-5 flex flex-col gap-4 ${cfg.glow} fade-in`}
            style={{ animationDelay: `${index * 0.05}s` }}
        >
            {/* 헤더: 등급 + 종목명 + 마켓 */}
            <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                        <span className={`${cfg.badge} text-xs font-bold px-2 py-0.5 rounded-md`}>
                            {signal.grade}
                        </span>
                        <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                            {signal.market}
                        </span>
                    </div>
                    <p className="font-bold text-white truncate">{signal.stock_name}</p>
                    <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                        {signal.stock_code} · {signal.sector}
                    </p>
                </div>

                {/* 등락률 + 점수 */}
                <div className="text-right shrink-0">
                    <p
                        className="text-lg font-bold tabular-nums"
                        style={{ color: isUp ? "var(--color-up)" : signal.change_pct < 0 ? "var(--color-down)" : "var(--text-muted)" }}
                    >
                        {isUp ? "+" : ""}{signal.change_pct?.toFixed(2)}%
                    </p>
                    <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                        {signal.score.total}점 / 12
                    </p>
                </div>
            </div>

            {/* 가격 정보 */}
            <div
                className="grid grid-cols-3 gap-2 p-3 rounded-lg text-center"
                style={{ background: "rgba(255,255,255,0.04)" }}
            >
                <StatBox label="진입가" value={`${signal.entry_price?.toLocaleString()}원`} />
                <StatBox
                    label="손절가"
                    value={`${signal.stop_price?.toLocaleString()}원`}
                />
                <StatBox
                    label="목표가"
                    value={`${signal.target_price?.toLocaleString()}원`}
                    highlight
                />
            </div>

            {/* 채점 항목 ScoreBar */}
            <div className="space-y-2">
                <p className="text-xs font-medium" style={{ color: "var(--text-muted)" }}>
                    채점 내역
                </p>
                {SCORE_ITEMS.map((item) => (
                    <ScoreBar key={item.label} {...item} />
                ))}
            </div>

            {/* LLM 분석 이유 */}
            {signal.score.llm_reason && (
                <div
                    className="px-3 py-2 rounded-lg text-xs leading-relaxed"
                    style={{ background: "rgba(99,102,241,0.06)", color: "var(--text-secondary)" }}
                >
                    🤖 {signal.score.llm_reason}
                </div>
            )}

            {/* 뉴스 + 차트 버튼 */}
            <div className="flex gap-2">
                {signal.news_items.length > 0 && (
                    <a
                        href={signal.news_items[0].url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex-1 text-center text-xs py-2 rounded-lg transition-colors"
                        style={{
                            background: "rgba(255,255,255,0.06)",
                            color: "var(--text-secondary)",
                        }}
                    >
                        📰 뉴스 보기
                    </a>
                )}
                <button
                    onClick={() => onOpenChart(signal.stock_code, signal.stock_name)}
                    className="flex-1 text-center text-xs py-2 rounded-lg transition-colors"
                    style={{
                        background: "rgba(255,255,255,0.06)",
                        color: "var(--text-secondary)",
                    }}
                >
                    📈 차트 보기
                </button>
            </div>
        </div>
    );
}

// ─── DataStatusBox ───
function DataStatusBox({ result }: { result: ClosingBetResult }) {
    return (
        <div
            className="card px-4 py-3 flex items-center justify-between"
            style={{ background: "rgba(255,255,255,0.03)" }}
        >
            <div className="flex gap-6">
                <StatBox label="분석일" value={result.date} />
                <StatBox label="총 후보" value={`${result.total_candidates}개`} />
                <StatBox label="시그널" value={`${result.filtered_count}개`} highlight />
                <StatBox label="처리 시간" value={`${(result.processing_time_ms / 1000).toFixed(1)}초`} />
            </div>
            <p className="text-xs hidden sm:block" style={{ color: "var(--text-muted)" }}>
                by engine/generator.py
            </p>
        </div>
    );
}

// ─── 스켈레톤 카드 ───
function SkeletonCard() {
    return (
        <div className="card p-5 flex flex-col gap-4">
            <div className="flex justify-between">
                <div className="space-y-2">
                    <div className="skeleton h-5 w-16 rounded" />
                    <div className="skeleton h-4 w-28 rounded" />
                </div>
                <div className="skeleton h-8 w-16 rounded" />
            </div>
            <div className="skeleton h-16 rounded-lg" />
            <div className="space-y-2">
                {Array.from({ length: 6 }).map((_, i) => (
                    <div key={i} className="skeleton h-3 rounded" />
                ))}
            </div>
        </div>
    );
}

// ─── 메인 페이지 ───
export default function JonggaV2Page() {
    const [result, setResult] = useState<ClosingBetResult | null>(null);
    const [loading, setLoading] = useState(true);
    const [running, setRunning] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [chartModal, setChartModal] = useState<{ code: string; name: string } | null>(null);
    const [sortBy, setSortBy] = useState<"grade" | "score">("grade");

    const fetchLatest = useCallback(async () => {
        try {
            const data = await closingBetAPI.getLatest();
            setResult(data);
            setError(null);
        } catch (e) {
            setError((e as Error).message);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchLatest();
    }, [fetchLatest]);

    // 전체 엔진 실행
    const handleRun = async () => {
        if (running) return;
        setRunning(true);
        try {
            const data = await closingBetAPI.run();
            setResult(data);
            setError(null);
        } catch (e) {
            setError(`실행 실패: ${(e as Error).message}`);
        } finally {
            setRunning(false);
        }
    };

    // 정렬된 시그널 목록
    const sortedSignals = result?.signals
        ? [...result.signals].sort((a, b) => {
            if (sortBy === "grade") {
                const order = { S: 0, A: 1, B: 2, C: 3 };
                return (order[a.grade] ?? 9) - (order[b.grade] ?? 9);
            }
            return b.score.total - a.score.total;
        })
        : [];

    return (
        <div className="flex-1 p-6 pb-20 md:pb-6 fade-in">
            {/* 헤더 */}
            <div className="flex flex-wrap items-center justify-between gap-3 mb-6">
                <div>
                    <h1 className="text-xl font-bold text-white">종가베팅 V2</h1>
                    <p className="text-sm mt-0.5" style={{ color: "var(--text-muted)" }}>
                        AI 12점 채점 시스템 시그널
                    </p>
                </div>

                <div className="flex items-center gap-2">
                    {/* 정렬 토글 */}
                    <div
                        className="flex rounded-lg overflow-hidden border"
                        style={{ borderColor: "var(--border-subtle)" }}
                    >
                        {(["grade", "score"] as const).map((opt) => (
                            <button
                                key={opt}
                                onClick={() => setSortBy(opt)}
                                className="px-3 py-1.5 text-xs transition-colors"
                                style={{
                                    background: sortBy === opt ? "rgba(255,255,255,0.08)" : "transparent",
                                    color: sortBy === opt ? "var(--text-primary)" : "var(--text-muted)",
                                }}
                            >
                                {opt === "grade" ? "등급순" : "점수순"}
                            </button>
                        ))}
                    </div>

                    {/* 엔진 실행 버튼 */}
                    <button
                        onClick={handleRun}
                        disabled={running}
                        className="px-4 py-1.5 text-xs font-medium rounded-lg transition-all"
                        style={{
                            background: running ? "rgba(255,255,255,0.04)" : "rgba(99,102,241,0.15)",
                            color: running ? "var(--text-muted)" : "#818cf8",
                            border: "1px solid rgba(99,102,241,0.3)",
                        }}
                    >
                        {running ? "⏳ 분석 중..." : "▶ 엔진 실행"}
                    </button>
                </div>
            </div>

            {/* 에러 */}
            {error && !loading && (
                <div className="card p-4 mb-4 border-rose-500/30 bg-rose-500/10">
                    <p className="text-sm text-rose-400">⚠️ {error}</p>
                    <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
                        Flask 서버 실행 후 &lsquo;엔진 실행&rsquo; 버튼을 눌러 분석을 시작하세요.
                    </p>
                </div>
            )}

            {/* 데이터 상태 박스 */}
            {result && !loading && (
                <div className="mb-5">
                    <DataStatusBox result={result} />
                </div>
            )}

            {/* 등급별 요약 배지 */}
            {result && result.by_grade && Object.keys(result.by_grade).length > 0 && (
                <div className="flex gap-2 mb-5 flex-wrap">
                    {Object.entries(result.by_grade).map(([grade, count]) => {
                        const cfg = GRADE_CONFIG[grade as keyof typeof GRADE_CONFIG] ?? GRADE_CONFIG.C;
                        return (
                            <span
                                key={grade}
                                className={`${cfg.badge} text-xs font-medium px-2.5 py-1 rounded-full`}
                            >
                                {cfg.emoji} {grade}등급 {count}개
                            </span>
                        );
                    })}
                </div>
            )}

            {/* 카드 그리드 */}
            {loading ? (
                <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
                    {Array.from({ length: 6 }).map((_, i) => <SkeletonCard key={i} />)}
                </div>
            ) : sortedSignals.length === 0 ? (
                <div className="card p-12 text-center">
                    <p className="text-4xl mb-3">📭</p>
                    <p className="font-medium text-white">시그널 없음</p>
                    <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>
                        오른쪽 상단 &apos;엔진 실행&apos; 버튼으로 분석을 시작하세요.
                    </p>
                </div>
            ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
                    {sortedSignals.map((signal, i) => (
                        <SignalCard
                            key={`${signal.stock_code}-${i}`}
                            signal={signal}
                            index={i}
                            onOpenChart={(code, name) => setChartModal({ code, name })}
                        />
                    ))}
                </div>
            )}

            {/* 차트 모달 */}
            {chartModal && (
                <ChartModal
                    symbol={chartModal.code}
                    name={chartModal.name}
                    onClose={() => setChartModal(null)}
                />
            )}
        </div>
    );
}
