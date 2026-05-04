"use client";

/**
 * VCP 시그널 테이블 페이지 (dashboard/kr/vcp/page.tsx)
 *
 * 설계 의도:
 * - 60초 자동 갱신으로 실시간 시그널 추적
 * - 등급 배지 + 수급 열로 빠른 종목 스캔 가능
 * - 진입가/손절가/목표가를 함께 표시해 리스크 관리 지원
 */

import { useEffect, useState, useCallback } from "react";
import { krAPI, type VCPSignal } from "@/lib/api";

// ─── 등급 배지 ───
function GradeBadge({ grade }: { grade: string }) {
    const cls = `badge-${grade.toLowerCase()}`;
    return (
        <span className={`${cls} text-xs font-bold px-2 py-0.5 rounded-md`}>
            {grade}
        </span>
    );
}

// ─── 등락률 셀 ───
function ChangePct({ value }: { value: number }) {
    const isUp = value > 0;
    return (
        <span
            className="font-medium tabular-nums"
            style={{ color: isUp ? "var(--color-up)" : value < 0 ? "var(--color-down)" : "var(--text-muted)" }}
        >
            {isUp ? "+" : ""}{value.toFixed(2)}%
        </span>
    );
}

// ─── 수급 셀 (단위: 억) ───
function FlowCell({ value }: { value: number }) {
    const billion = Math.round(value / 1e8);
    const isPos = billion > 0;
    return (
        <span
            className="tabular-nums text-sm"
            style={{ color: isPos ? "var(--color-up)" : billion < 0 ? "var(--color-down)" : "var(--text-muted)" }}
        >
            {isPos ? "+" : ""}{billion.toLocaleString()}억
        </span>
    );
}

// ─── 스켈레톤 행 ───
function SkeletonRow() {
    return (
        <tr>
            {Array.from({ length: 8 }).map((_, i) => (
                <td key={i} className="px-4 py-3">
                    <div className="skeleton h-4 rounded w-full" />
                </td>
            ))}
        </tr>
    );
}

// ─── 메인 페이지 ───
export default function VCPSignalsPage() {
    const [signals, setSignals] = useState<VCPSignal[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
    const [countdown, setCountdown] = useState(60);

    const fetchSignals = useCallback(async () => {
        try {
            const data = await krAPI.getSignals();
            // Flask가 { signals: [...], count: N } 구조로 반환하므로 .signals 추출
            setSignals(Array.isArray(data.signals) ? data.signals : []);
            setLastUpdated(new Date());
            setCountdown(60);
            setError(null);
        } catch (e) {
            setError((e as Error).message);
        } finally {
            setLoading(false);
        }
    }, []);


    useEffect(() => {
        fetchSignals();
        const interval = setInterval(fetchSignals, 60_000);
        return () => clearInterval(interval);
    }, [fetchSignals]);

    // 카운트다운 타이머
    useEffect(() => {
        const timer = setInterval(() => {
            setCountdown((c) => (c > 0 ? c - 1 : 60));
        }, 1000);
        return () => clearInterval(timer);
    }, []);

    return (
        <div className="flex-1 p-6 pb-20 md:pb-6 fade-in">
            {/* 헤더 */}
            <div className="flex items-center justify-between mb-6">
                <div>
                    <h1 className="text-xl font-bold text-white">VCP 시그널</h1>
                    <p className="text-sm mt-0.5" style={{ color: "var(--text-muted)" }}>
                        수급 + VCP 패턴 탐지 종목
                    </p>
                </div>
                <div className="text-right">
                    {lastUpdated && (
                        <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                            {lastUpdated.toLocaleTimeString("ko-KR")} 갱신
                        </p>
                    )}
                    <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                        {countdown}초 후 자동 갱신
                    </p>
                </div>
            </div>

            {/* 에러 */}
            {error && !loading && (
                <div className="card p-4 mb-4 border-rose-500/30 bg-rose-500/10">
                    <p className="text-sm text-rose-400">⚠️ {error}</p>
                </div>
            )}

            {/* 시그널 수 요약 */}
            {!loading && signals.length > 0 && (
                <div className="flex gap-3 mb-4">
                    <span className="text-sm" style={{ color: "var(--text-secondary)" }}>
                        총 <span className="text-white font-bold">{signals.length}</span>개 시그널
                    </span>
                </div>
            )}

            {/* 테이블 */}
            <div
                className="card overflow-hidden"
                style={{ overflowX: "auto" }}
            >
                <table className="w-full text-sm text-left min-w-[700px]">
                    <thead>
                        <tr
                            className="text-xs uppercase"
                            style={{
                                color: "var(--text-muted)",
                                borderBottom: "1px solid var(--border-subtle)",
                            }}
                        >
                            {["#", "종목명", "마켓", "등락률", "점수", "외인 수급", "기관 수급", "진입가"].map(
                                (h) => (
                                    <th key={h} className="px-4 py-3 font-medium">
                                        {h}
                                    </th>
                                )
                            )}
                        </tr>
                    </thead>
                    <tbody>
                        {loading
                            ? Array.from({ length: 8 }).map((_, i) => <SkeletonRow key={i} />)
                            : signals.length === 0
                                ? (
                                    <tr>
                                        <td colSpan={8} className="px-4 py-12 text-center" style={{ color: "var(--text-muted)" }}>
                                            시그널 데이터가 없습니다.<br />
                                            <span className="text-xs mt-1 block">VCP 스캔을 먼저 실행하세요.</span>
                                        </td>
                                    </tr>
                                )
                                : signals.map((sig, i) => (
                                    <tr
                                        key={sig.ticker}
                                        className="transition-colors"
                                        style={{
                                            borderBottom: "1px solid var(--border-subtle)",
                                        }}
                                        onMouseEnter={(e) => {
                                            (e.currentTarget as HTMLElement).style.background = "rgba(255,255,255,0.03)";
                                        }}
                                        onMouseLeave={(e) => {
                                            (e.currentTarget as HTMLElement).style.background = "transparent";
                                        }}
                                    >
                                        <td className="px-4 py-3" style={{ color: "var(--text-muted)" }}>
                                            {i + 1}
                                        </td>
                                        <td className="px-4 py-3">
                                            <div>
                                                <p className="font-medium text-white">{sig.name}</p>
                                                <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                                                    {sig.ticker}
                                                </p>
                                            </div>
                                        </td>
                                        <td className="px-4 py-3 text-xs" style={{ color: "var(--text-muted)" }}>
                                            {sig.market}
                                        </td>
                                        <td className="px-4 py-3">
                                            <ChangePct value={sig.change_pct} />
                                        </td>
                                        <td className="px-4 py-3">
                                            <div className="flex items-center gap-2">
                                                <div
                                                    className="h-1.5 rounded-full"
                                                    style={{
                                                        width: `${Math.min(sig.score, 100)}%`,
                                                        maxWidth: "60px",
                                                        background: "linear-gradient(90deg, #818cf8, #f43f5e)",
                                                    }}
                                                />
                                                <span className="text-white font-medium tabular-nums">
                                                    {typeof sig.score === "number" ? sig.score.toFixed(0) : sig.score}
                                                </span>
                                            </div>
                                        </td>
                                        <td className="px-4 py-3">
                                            <FlowCell value={sig.foreign_net} />
                                        </td>
                                        <td className="px-4 py-3">
                                            <FlowCell value={sig.inst_net} />
                                        </td>
                                        <td className="px-4 py-3 font-medium text-white tabular-nums">
                                            {sig.entry_price?.toLocaleString()}원
                                        </td>
                                    </tr>
                                ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
