"use client";

/**
 * 시그널 히스토리 화면 (dashboard/history/page.tsx)
 *
 * 설계 의도:
 * - 전략 A/B + 등급 필터로 원하는 시그널만 필터링
 * - 상승=빨강, 하락=파랑 한국 주식 컨벤션 적용
 * - HistorySummary로 필터 결과 통계 즉시 표시
 */

import { useEffect, useState, useCallback } from "react";
import { performanceAPI, type SignalRow } from "@/lib/api";

// ─── 청산 이유 한글 ───
const REASON_LABELS: Record<string, string> = {
    trailing_stop: "트레일링 스탑",
    time_exit:     "5일 타임컷",
    target_hit:    "목표가 도달",
    stop_loss:     "손절",
    partial:       "분할 익절",
    manual:        "수동 청산",
};

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

// ─── FilterBar: 전략 + 등급 필터 버튼 ───
const STRATEGY_FILTERS = [
    { value: "",       label: "전체" },
    { value: "close",  label: "전략 A (종가)" },
    { value: "open",   label: "전략 B (시초가)" },
];

const GRADE_FILTERS = ["전체", "S", "A", "B", "C"];

function FilterBar({
    strategy,
    onStrategy,
    grade,
    onGrade,
}: {
    strategy: string;
    onStrategy: (v: string) => void;
    grade: string;
    onGrade: (v: string) => void;
}) {
    return (
        <div className="flex flex-wrap gap-3">
            {/* 전략 필터 */}
            <div
                className="flex rounded-lg overflow-hidden border"
                style={{ borderColor: "var(--border-subtle)" }}
            >
                {STRATEGY_FILTERS.map((f) => (
                    <button
                        key={f.value}
                        onClick={() => onStrategy(f.value)}
                        className="px-3 py-1.5 text-xs transition-colors"
                        style={{
                            background: strategy === f.value
                                ? "rgba(255,255,255,0.08)"
                                : "transparent",
                            color: strategy === f.value
                                ? "var(--text-primary)"
                                : "var(--text-muted)",
                        }}
                    >
                        {f.label}
                    </button>
                ))}
            </div>

            {/* 등급 필터 */}
            <div
                className="flex rounded-lg overflow-hidden border"
                style={{ borderColor: "var(--border-subtle)" }}
            >
                {GRADE_FILTERS.map((g) => (
                    <button
                        key={g}
                        onClick={() => onGrade(g === "전체" ? "" : g)}
                        className="px-3 py-1.5 text-xs transition-colors"
                        style={{
                            background: (g === "전체" ? "" : g) === grade
                                ? "rgba(255,255,255,0.08)"
                                : "transparent",
                            color: (g === "전체" ? "" : g) === grade
                                ? "var(--text-primary)"
                                : "var(--text-muted)",
                        }}
                    >
                        {g}
                    </button>
                ))}
            </div>
        </div>
    );
}

// ─── HistorySummary: 필터 기준 통계 ───
function HistorySummary({ signals }: { signals: SignalRow[] }) {
    const closed = signals.filter((s) => s.return_pct != null);
    const wins = closed.filter((s) => (s.return_pct ?? 0) > 0);
    const avgReturn =
        closed.length > 0
            ? closed.reduce((sum, s) => sum + (s.return_pct ?? 0), 0) / closed.length
            : 0;
    const wr = closed.length > 0 ? (wins.length / closed.length) * 100 : 0;

    const stats = [
        { label: "시그널", value: `${signals.length}건` },
        { label: "청산 완료", value: `${closed.length}건` },
        { label: "승률", value: `${wr.toFixed(1)}%`, color: wr >= 50 ? "var(--color-up)" : "var(--color-down)" },
        {
            label: "평균 EV",
            value: `${avgReturn >= 0 ? "+" : ""}${avgReturn.toFixed(2)}%`,
            color: avgReturn >= 2 ? "var(--color-up)" : avgReturn < 0 ? "var(--color-down)" : "var(--text-muted)",
        },
    ];

    return (
        <div
            className="card px-4 py-3 flex flex-wrap gap-6"
            style={{ background: "rgba(255,255,255,0.02)" }}
        >
            {stats.map((s) => (
                <div key={s.label}>
                    <p className="text-xs" style={{ color: "var(--text-muted)" }}>{s.label}</p>
                    <p
                        className="text-base font-bold tabular-nums mt-0.5"
                        style={{ color: s.color ?? "var(--text-primary)" }}
                    >
                        {s.value}
                    </p>
                </div>
            ))}
        </div>
    );
}

// ─── HistoryTable 행 ───
function HistoryRow({ signal }: { signal: SignalRow }) {
    const ret = signal.return_pct ?? null;
    const retColor =
        ret === null
            ? "var(--text-muted)"
            : ret > 0
                ? "var(--color-up)"
                : ret < 0
                    ? "var(--color-down)"
                    : "var(--text-muted)";

    return (
        <tr
            className="border-b transition-colors hover:bg-white/[0.02]"
            style={{ borderColor: "var(--border-subtle)" }}
        >
            <td className="px-3 py-2.5 text-xs whitespace-nowrap" style={{ color: "var(--text-muted)" }}>
                {signal.signal_date}
            </td>
            <td className="px-3 py-2.5">
                <p className="text-xs font-medium text-white">{signal.ticker}</p>
                <p className="text-[10px]" style={{ color: "var(--text-muted)" }}>{signal.name}</p>
            </td>
            <td className="px-3 py-2.5">
                <GradeBadge grade={signal.grade} />
            </td>
            <td className="px-3 py-2.5 text-xs tabular-nums text-white whitespace-nowrap">
                {signal.entry_price?.toLocaleString()}원
            </td>
            <td className="px-3 py-2.5 text-xs tabular-nums whitespace-nowrap" style={{ color: "var(--text-muted)" }}>
                {signal.exit_price != null ? `${signal.exit_price.toLocaleString()}원` : "—"}
            </td>
            <td
                className="px-3 py-2.5 text-xs font-bold tabular-nums whitespace-nowrap"
                style={{ color: retColor }}
            >
                {ret != null ? `${ret > 0 ? "+" : ""}${ret.toFixed(2)}%` : "—"}
            </td>
            <td className="px-3 py-2.5 text-xs whitespace-nowrap" style={{ color: "var(--text-muted)" }}>
                {signal.exit_date ?? "진행 중"}
            </td>
            <td className="px-3 py-2.5 text-xs whitespace-nowrap" style={{ color: "var(--text-secondary)" }}>
                {signal.days_held != null ? `${signal.days_held}일` : "—"}
            </td>
            <td className="px-3 py-2.5 text-xs whitespace-nowrap" style={{ color: "var(--text-secondary)" }}>
                {signal.exit_reason
                    ? REASON_LABELS[signal.exit_reason] ?? signal.exit_reason
                    : "활성"}
            </td>
        </tr>
    );
}

// ─── 스켈레톤 ───
function SkeletonHistory() {
    return (
        <div className="flex flex-col gap-4">
            <div className="skeleton h-10 rounded-lg w-80" />
            <div className="skeleton h-14 rounded-xl" />
            <div className="skeleton h-64 rounded-xl" />
        </div>
    );
}

// ─── 메인 페이지 ───
export default function HistoryPage() {
    const [allSignals, setAllSignals] = useState<SignalRow[]>([]);
    const [total, setTotal] = useState(0);
    const [page, setPage] = useState(1);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    // 클라이언트 사이드 필터
    const [strategy, setStrategy] = useState("");
    const [grade, setGrade] = useState("");

    const PER_PAGE = 10;

    const fetchData = useCallback(async (p: number, strat: string) => {
        try {
            setLoading(true);
            const data = await performanceAPI.getSignalHistory(p, strat);
            setAllSignals(data.signals);
            setTotal(data.total);
            setError(null);
        } catch (e) {
            setError((e as Error).message);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        setPage(1);
        fetchData(1, strategy);
    }, [fetchData, strategy]);

    // 등급 필터는 클라이언트 사이드
    const filtered = grade
        ? allSignals.filter((s) => s.grade === grade)
        : allSignals;

    const totalPages = Math.ceil(total / PER_PAGE);

    return (
        <div className="flex-1 p-6 pb-20 md:pb-6 fade-in">
            {/* 헤더 */}
            <div className="mb-6">
                <h1 className="text-xl font-bold text-white">시그널 히스토리</h1>
                <p className="text-sm mt-0.5" style={{ color: "var(--text-muted)" }}>
                    전체 시그널 기록 — 전략 / 등급 필터 지원
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
                <SkeletonHistory />
            ) : (
                <div className="flex flex-col gap-4">
                    {/* 필터 바 */}
                    <FilterBar
                        strategy={strategy}
                        onStrategy={(v) => setStrategy(v)}
                        grade={grade}
                        onGrade={(v) => setGrade(v)}
                    />

                    {/* 필터 결과 요약 */}
                    <HistorySummary signals={filtered} />

                    {/* 히스토리 테이블 */}
                    <div className="card overflow-hidden">
                        <div className="overflow-x-auto">
                            <table className="w-full min-w-[720px]">
                                <thead>
                                    <tr style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                                        {["시그널일", "종목", "등급", "진입가", "청산가", "수익률", "청산일", "보유일", "청산 이유"].map((h) => (
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
                                    {filtered.length === 0 ? (
                                        <tr>
                                            <td
                                                colSpan={9}
                                                className="px-4 py-10 text-center text-sm"
                                                style={{ color: "var(--text-muted)" }}
                                            >
                                                해당 조건의 시그널 없음
                                            </td>
                                        </tr>
                                    ) : (
                                        filtered.map((s) => (
                                            <HistoryRow key={s.signal_id} signal={s} />
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
                                    onClick={() => {
                                        const np = Math.max(1, page - 1);
                                        setPage(np);
                                        fetchData(np, strategy);
                                    }}
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
                                    {page} / {totalPages} (총 {total}건)
                                </p>
                                <button
                                    onClick={() => {
                                        const np = Math.min(totalPages, page + 1);
                                        setPage(np);
                                        fetchData(np, strategy);
                                    }}
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
