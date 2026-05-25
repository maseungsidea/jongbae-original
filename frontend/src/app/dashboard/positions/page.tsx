"use client";

/**
 * 포지션 & 자금 관리 화면 (dashboard/positions/page.tsx)
 *
 * 설계 의도:
 * - 활성 포지션을 카드 그리드로 시각화
 * - CapitalSummary로 자금 배분 현황 파악
 * - trailing_stop vs 진입가 대비 상태 표시
 */

import { useEffect, useState, useCallback } from "react";
import { performanceAPI, type SignalRow } from "@/lib/api";

// ─── 등급 설정 ───
const GRADE_CONFIG = {
    S: { badge: "badge-s", glow: "card-glow-indigo", emoji: "💎" },
    A: { badge: "badge-a", glow: "card-glow-rose",   emoji: "🔥" },
    B: { badge: "badge-b", glow: "card-glow-blue",   emoji: "✅" },
    C: { badge: "badge-c", glow: "",                 emoji: "⬜" },
};

// ─── CapitalSummary: 자금 현황 바 ───
function CapitalSummary({
    positions,
    budget = 50_000_000,
}: {
    positions: SignalRow[];
    budget?: number;
}) {
    const allocated = positions.reduce((sum, p) => sum + (p.entry_price ?? 0) * 10, 0);
    const usedPct = Math.min((allocated / budget) * 100, 100);
    const count = positions.length;

    return (
        <div className="card p-4 fade-in">
            <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
                <div className="flex items-center gap-3">
                    <span className="text-xl">💼</span>
                    <div>
                        <p className="text-sm font-medium text-white">자금 현황</p>
                        <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                            활성 포지션 {count}건
                        </p>
                    </div>
                </div>
                <div className="flex gap-4">
                    <div className="text-right">
                        <p className="text-xs" style={{ color: "var(--text-muted)" }}>예산</p>
                        <p className="text-sm font-bold text-white tabular-nums">
                            {budget.toLocaleString()}원
                        </p>
                    </div>
                    <div className="text-right">
                        <p className="text-xs" style={{ color: "var(--text-muted)" }}>포지션 수</p>
                        <p className="text-sm font-bold tabular-nums" style={{ color: "var(--color-up)" }}>
                            {count}건
                        </p>
                    </div>
                </div>
            </div>
            <div
                className="h-2 rounded-full overflow-hidden"
                style={{ background: "rgba(255,255,255,0.06)" }}
            >
                <div
                    className="h-full rounded-full transition-all duration-700"
                    style={{
                        width: `${usedPct}%`,
                        background: usedPct > 80
                            ? "var(--gate-red)"
                            : usedPct > 50
                                ? "var(--gate-yellow)"
                                : "var(--gate-green)",
                    }}
                />
            </div>
        </div>
    );
}

// ─── InfoRow: 카드 내 정보 행 ───
function InfoRow({ label, value, color }: { label: string; value: string; color?: string }) {
    return (
        <div className="flex items-center justify-between">
            <span className="text-xs" style={{ color: "var(--text-muted)" }}>{label}</span>
            <span
                className="text-xs font-medium tabular-nums"
                style={{ color: color ?? "var(--text-secondary)" }}
            >
                {value}
            </span>
        </div>
    );
}

// ─── PositionCard: 포지션 1개 카드 ───
function PositionCard({ signal, index }: { signal: SignalRow; index: number }) {
    const cfg = GRADE_CONFIG[signal.grade as keyof typeof GRADE_CONFIG] ?? GRADE_CONFIG.C;

    // 트레일링 스탑이 진입가 위에 있으면 수익 보호 중
    const stopAboveEntry =
        signal.trailing_stop != null &&
        signal.entry_price != null &&
        signal.trailing_stop > signal.entry_price;

    const upside =
        signal.target_price && signal.entry_price
            ? (((signal.target_price - signal.entry_price) / signal.entry_price) * 100).toFixed(1)
            : null;

    const stopLoss =
        signal.stop_price && signal.entry_price
            ? (((signal.stop_price - signal.entry_price) / signal.entry_price) * 100).toFixed(1)
            : null;

    const daysHeld = signal.days_held ?? 0;
    const daysLeft = Math.max(0, 5 - daysHeld);

    return (
        <div
            className={`card p-5 flex flex-col gap-4 ${cfg.glow} fade-in`}
            style={{ animationDelay: `${index * 0.06}s` }}
        >
            {/* 헤더 */}
            <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                        <span className={`${cfg.badge} text-xs font-bold px-2 py-0.5 rounded-md`}>
                            {signal.grade}
                        </span>
                        <span
                            className="text-xs px-2 py-0.5 rounded-md"
                            style={{
                                background: signal.status === "entered"
                                    ? "rgba(74,222,128,0.1)"
                                    : "rgba(250,204,21,0.1)",
                                color: signal.status === "entered"
                                    ? "var(--gate-green)"
                                    : "var(--gate-yellow)",
                            }}
                        >
                            {signal.status === "entered" ? "진입 완료" : "대기 중"}
                        </span>
                    </div>
                    <p className="font-bold text-white truncate">{signal.name}</p>
                    <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                        {signal.ticker}
                    </p>
                </div>

                {/* 보유일 */}
                <div className="text-right shrink-0">
                    <p className="text-2xl font-bold tabular-nums text-white">{daysHeld}</p>
                    <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                        일째 / 잔여 {daysLeft}일
                    </p>
                </div>
            </div>

            {/* 가격 정보 */}
            <div
                className="rounded-lg p-3 flex flex-col gap-2"
                style={{ background: "rgba(255,255,255,0.03)" }}
            >
                <InfoRow
                    label="진입가"
                    value={`${signal.entry_price?.toLocaleString()}원`}
                    color="var(--text-primary)"
                />
                <InfoRow
                    label="목표가"
                    value={upside ? `${signal.target_price?.toLocaleString()}원 (+${upside}%)` : "—"}
                    color="var(--color-up)"
                />
                <InfoRow
                    label="손절가"
                    value={stopLoss ? `${signal.stop_price?.toLocaleString()}원 (${stopLoss}%)` : "—"}
                    color="var(--color-down)"
                />
                {signal.trailing_stop != null && (
                    <InfoRow
                        label="트레일링 스탑"
                        value={`${signal.trailing_stop.toLocaleString()}원`}
                        color={stopAboveEntry ? "var(--gate-green)" : "var(--gate-yellow)"}
                    />
                )}
                {signal.peak_price != null && (
                    <InfoRow
                        label="고점"
                        value={`${signal.peak_price.toLocaleString()}원`}
                    />
                )}
            </div>

            {/* 수익 보호 상태 표시 */}
            {stopAboveEntry && (
                <div
                    className="text-xs px-3 py-2 rounded-lg"
                    style={{
                        background: "rgba(74,222,128,0.08)",
                        color: "var(--gate-green)",
                    }}
                >
                    ✅ 트레일링 스탑이 진입가 위 — 수익 보호 중
                </div>
            )}

            <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                시그널: {signal.signal_date}
            </p>
        </div>
    );
}

// ─── 스켈레톤 ───
function SkeletonPositions() {
    return (
        <div className="flex flex-col gap-5">
            <div className="skeleton h-20 rounded-xl" />
            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
                {Array.from({ length: 3 }).map((_, i) => (
                    <div key={i} className="skeleton h-64 rounded-xl" />
                ))}
            </div>
        </div>
    );
}

// ─── 메인 페이지 ───
export default function PositionsPage() {
    const [positions, setPositions] = useState<SignalRow[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const fetchData = useCallback(async () => {
        try {
            setLoading(true);
            const data = await performanceAPI.getSignalHistory(1, "open");
            // 활성(pending/entered) 필터
            const active = data.signals.filter(
                (s) => s.status === "pending" || s.status === "entered"
            );
            setPositions(active);
            setError(null);
        } catch (e) {
            setError((e as Error).message);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchData();
    }, [fetchData]);

    return (
        <div className="flex-1 p-6 pb-20 md:pb-6 fade-in">
            {/* 헤더 */}
            <div className="flex flex-wrap items-center justify-between gap-3 mb-6">
                <div>
                    <h1 className="text-xl font-bold text-white">포지션 관리</h1>
                    <p className="text-sm mt-0.5" style={{ color: "var(--text-muted)" }}>
                        활성 포지션 & 자금 현황
                    </p>
                </div>
                <button
                    onClick={fetchData}
                    className="text-xs px-3 py-1.5 rounded-lg transition-colors"
                    style={{
                        background: "rgba(255,255,255,0.06)",
                        color: "var(--text-secondary)",
                    }}
                >
                    새로고침
                </button>
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
                <SkeletonPositions />
            ) : (
                <div className="flex flex-col gap-5">
                    {/* 자금 현황 */}
                    <CapitalSummary positions={positions} />

                    {/* 포지션 카드 그리드 */}
                    {positions.length === 0 ? (
                        <div className="card p-12 text-center">
                            <p className="text-4xl mb-3">📭</p>
                            <p className="font-medium text-white">활성 포지션 없음</p>
                            <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>
                                오늘 VCP 스캔 후 시그널이 추가됩니다.
                            </p>
                        </div>
                    ) : (
                        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
                            {positions.map((p, i) => (
                                <PositionCard key={p.signal_id} signal={p} index={i} />
                            ))}
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
