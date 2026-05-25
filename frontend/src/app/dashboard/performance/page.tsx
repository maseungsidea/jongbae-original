"use client";

/**
 * 수익률 트래킹 화면 (dashboard/performance/page.tsx)
 *
 * 설계 의도:
 * - 4개 KPI StatCard로 핵심 성과를 즉각 파악
 * - 청산 이유별 가로 막대 차트로 패턴 파악
 * - 페이지네이션 히스토리 테이블 (10행/페이지)
 * - 한국 주식 컨벤션: 상승=빨강, 하락=파랑
 */

import { useEffect, useState, useCallback } from "react";
import {
    performanceAPI,
    type PerformanceSummary,
    type SignalRow,
} from "@/lib/api";

// ─── 청산 이유 한글 라벨 ───
const REASON_LABELS: Record<string, string> = {
    trailing_stop: "트레일링 스탑",
    time_exit:     "5일 타임 컷",
    target_hit:    "목표가 도달",
    stop_loss:     "손절",
    partial:       "분할 익절",
    manual:        "수동 청산",
};

// ─── StatCard: KPI 박스 ───
function StatCard({
    label,
    value,
    sub,
    highlight,
    icon,
}: {
    label: string;
    value: string;
    sub?: string;
    highlight?: "up" | "down" | "none";
    icon: string;
}) {
    const valueColor =
        highlight === "up"
            ? "var(--color-up)"
            : highlight === "down"
                ? "var(--color-down)"
                : "var(--text-primary)";

    return (
        <div className="card p-4 flex flex-col gap-2 fade-in">
            <div className="flex items-center gap-2">
                <span className="text-lg">{icon}</span>
                <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                    {label}
                </p>
            </div>
            <p className="text-2xl font-bold tabular-nums" style={{ color: valueColor }}>
                {value}
            </p>
            {sub && (
                <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                    {sub}
                </p>
            )}
        </div>
    );
}

// ─── ByReasonChart: 청산 이유별 막대 차트 (CSS flex) ───
function ByReasonChart({ byReason }: { byReason: Record<string, number> }) {
    const entries = Object.entries(byReason).sort((a, b) => b[1] - a[1]);
    const maxVal = Math.max(...entries.map(([, v]) => v), 1);

    return (
        <div className="card p-5">
            <p className="text-sm font-medium text-white mb-4">청산 이유별 건수</p>
            <div className="flex flex-col gap-3">
                {entries.map(([reason, count]) => {
                    const pct = (count / maxVal) * 100;
                    return (
                        <div key={reason} className="flex items-center gap-3">
                            <span
                                className="text-xs w-24 shrink-0 text-right"
                                style={{ color: "var(--text-secondary)" }}
                            >
                                {REASON_LABELS[reason] ?? reason}
                            </span>
                            <div
                                className="flex-1 rounded-full h-2"
                                style={{ background: "rgba(255,255,255,0.06)" }}
                            >
                                <div
                                    className="h-2 rounded-full transition-all duration-700"
                                    style={{
                                        width: `${pct}%`,
                                        background:
                                            reason === "target_hit"
                                                ? "var(--color-up)"
                                                : reason === "stop_loss"
                                                    ? "var(--color-down)"
                                                    : "var(--gate-yellow)",
                                    }}
                                />
                            </div>
                            <span
                                className="text-xs w-6 text-right tabular-nums text-white shrink-0"
                            >
                                {count}
                            </span>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}

// ─── 등급 배지 ───
function GradeBadge({ grade }: { grade: string }) {
    const cls =
        grade === "S" ? "badge-s"
            : grade === "A" ? "badge-a"
                : grade === "B" ? "badge-b"
                    : "badge-c";
    return (
        <span className={`${cls} text-xs font-bold px-2 py-0.5 rounded-md`}>
            {grade}
        </span>
    );
}

// ─── TradeRow: 테이블 행 ───
function TradeRow({ signal }: { signal: SignalRow }) {
    const ret = signal.return_pct ?? null;
    const retColor =
        ret === null ? "var(--text-muted)"
            : ret > 0 ? "var(--color-up)"
                : ret < 0 ? "var(--color-down)"
                    : "var(--text-muted)";

    return (
        <tr
            className="border-b transition-colors"
            style={{ borderColor: "var(--border-subtle)" }}
        >
            <td className="px-3 py-2.5 text-xs whitespace-nowrap" style={{ color: "var(--text-muted)" }}>
                {signal.signal_date}
            </td>
            <td className="px-3 py-2.5">
                <div>
                    <p className="text-xs font-medium text-white">{signal.ticker}</p>
                    <p className="text-[10px]" style={{ color: "var(--text-muted)" }}>{signal.name}</p>
                </div>
            </td>
            <td className="px-3 py-2.5">
                <GradeBadge grade={signal.grade} />
            </td>
            <td className="px-3 py-2.5 text-xs tabular-nums text-white">
                {signal.entry_price?.toLocaleString()}
            </td>
            <td className="px-3 py-2.5 text-xs tabular-nums" style={{ color: "var(--text-muted)" }}>
                {signal.exit_price?.toLocaleString() ?? "—"}
            </td>
            <td
                className="px-3 py-2.5 text-xs font-bold tabular-nums"
                style={{ color: retColor }}
            >
                {ret !== null
                    ? `${ret > 0 ? "+" : ""}${ret.toFixed(2)}%`
                    : "—"}
            </td>
            <td className="px-3 py-2.5 text-xs" style={{ color: "var(--text-muted)" }}>
                {signal.days_held != null ? `${signal.days_held}일` : "—"}
            </td>
            <td className="px-3 py-2.5 text-xs" style={{ color: "var(--text-secondary)" }}>
                {signal.exit_reason
                    ? REASON_LABELS[signal.exit_reason] ?? signal.exit_reason
                    : "활성"}
            </td>
        </tr>
    );
}

// ─── 스켈레톤 ───
function SkeletonPerf() {
    return (
        <div className="flex flex-col gap-5">
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                {Array.from({ length: 4 }).map((_, i) => (
                    <div key={i} className="skeleton h-24 rounded-xl" />
                ))}
            </div>
            <div className="skeleton h-40 rounded-xl" />
            <div className="skeleton h-64 rounded-xl" />
        </div>
    );
}

// ─── 메인 페이지 ───
export default function PerformancePage() {
    const [summary, setSummary] = useState<PerformanceSummary | null>(null);
    const [signals, setSignals] = useState<SignalRow[]>([]);
    const [total, setTotal] = useState(0);
    const [page, setPage] = useState(1);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const PER_PAGE = 10;

    const fetchData = useCallback(async (p: number) => {
        try {
            setLoading(true);
            const [sumData, histData] = await Promise.all([
                performanceAPI.getSummary(),
                performanceAPI.getSignalHistory(p),
            ]);
            setSummary(sumData);
            setSignals(histData.signals);
            setTotal(histData.total);
            setError(null);
        } catch (e) {
            setError((e as Error).message);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchData(page);
    }, [fetchData, page]);

    const totalPages = Math.ceil(total / PER_PAGE);

    return (
        <div className="flex-1 p-6 pb-20 md:pb-6 fade-in">
            {/* 헤더 */}
            <div className="mb-6">
                <h1 className="text-xl font-bold text-white">수익률 추적</h1>
                <p className="text-sm mt-0.5" style={{ color: "var(--text-muted)" }}>
                    실현 성과 & 시그널 히스토리
                </p>
            </div>

            {error && !loading && (
                <div
                    className="card p-4 mb-5"
                    style={{
                        background: "rgba(248,113,113,0.06)",
                        borderColor: "rgba(248,113,113,0.25)",
                    }}
                >
                    <p className="text-sm" style={{ color: "var(--gate-red)" }}>
                        ⚠️ {error}
                    </p>
                </div>
            )}

            {loading ? (
                <SkeletonPerf />
            ) : (
                <div className="flex flex-col gap-5">
                    {/* KPI 카드 4개 */}
                    {summary && (
                        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                            <StatCard
                                icon="📊"
                                label="총 거래 수"
                                value={`${summary.total}건`}
                                sub="전체 시그널 기준"
                            />
                            <StatCard
                                icon="🎯"
                                label="승률"
                                value={`${(summary.win_rate * 100).toFixed(1)}%`}
                                highlight={summary.win_rate >= 0.5 ? "up" : "down"}
                                sub="목표 ≥ 50%"
                            />
                            <StatCard
                                icon="💹"
                                label="평균 수익률 (EV)"
                                value={`${summary.avg_return >= 0 ? "+" : ""}${summary.avg_return.toFixed(2)}%`}
                                highlight={summary.avg_return >= 2 ? "up" : summary.avg_return < 0 ? "down" : "none"}
                                sub="목표 ≥ +2.0%"
                            />
                            <StatCard
                                icon="📉"
                                label="평균 보유일"
                                value="—"
                                sub="5일 타임컷 기준"
                            />
                        </div>
                    )}

                    {/* 청산 이유 차트 */}
                    {summary && Object.keys(summary.by_reason).length > 0 && (
                        <ByReasonChart byReason={summary.by_reason} />
                    )}

                    {/* 시그널 히스토리 테이블 */}
                    <div className="card overflow-hidden">
                        <div
                            className="px-4 py-3 border-b flex items-center justify-between"
                            style={{ borderColor: "var(--border-subtle)" }}
                        >
                            <p className="text-sm font-medium text-white">시그널 히스토리</p>
                            <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                                총 {total}건
                            </p>
                        </div>

                        <div className="overflow-x-auto">
                            <table className="w-full min-w-[600px]">
                                <thead>
                                    <tr style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                                        {["날짜", "종목", "등급", "진입가", "청산가", "수익률", "보유일", "청산 이유"].map((h) => (
                                            <th
                                                key={h}
                                                className="px-3 py-2.5 text-left text-xs font-medium"
                                                style={{ color: "var(--text-muted)" }}
                                            >
                                                {h}
                                            </th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody>
                                    {signals.length === 0 ? (
                                        <tr>
                                            <td
                                                colSpan={8}
                                                className="px-4 py-8 text-center text-sm"
                                                style={{ color: "var(--text-muted)" }}
                                            >
                                                데이터 없음
                                            </td>
                                        </tr>
                                    ) : (
                                        signals.map((s) => (
                                            <TradeRow key={s.signal_id} signal={s} />
                                        ))
                                    )}
                                </tbody>
                            </table>
                        </div>

                        {/* 페이지네이션 */}
                        {totalPages > 1 && (
                            <div
                                className="flex items-center justify-between px-4 py-3 border-t"
                                style={{ borderColor: "var(--border-subtle)" }}
                            >
                                <button
                                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                                    disabled={page === 1}
                                    className="text-xs px-3 py-1.5 rounded-lg transition-colors disabled:opacity-30"
                                    style={{
                                        background: "rgba(255,255,255,0.06)",
                                        color: "var(--text-secondary)",
                                    }}
                                >
                                    ← 이전
                                </button>
                                <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                                    {page} / {totalPages}
                                </p>
                                <button
                                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                                    disabled={page === totalPages}
                                    className="text-xs px-3 py-1.5 rounded-lg transition-colors disabled:opacity-30"
                                    style={{
                                        background: "rgba(255,255,255,0.06)",
                                        color: "var(--text-secondary)",
                                    }}
                                >
                                    다음 →
                                </button>
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}
