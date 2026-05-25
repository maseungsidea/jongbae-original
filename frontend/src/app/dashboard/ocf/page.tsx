"use client";

/**
 * OCF 오버나이트 리스크 화면 (dashboard/ocf/page.tsx)
 *
 * 설계 의도:
 * - 미국장 전날 리스크 체크 결과를 한눈에 파악
 * - SeverityBanner로 즉각적인 위험도 인지
 * - 4개 핵심 지표를 MetricCard로 시각화
 * - 60초 자동 갱신
 */

import { useEffect, useState, useCallback } from "react";
import { ocfAPI, type OCFResult, type OCFFlag } from "@/lib/api";

// ─── 심각도 설정 ───
const SEVERITY_CONFIG = {
    OK:      { bg: "rgba(74,222,128,0.08)", border: "rgba(74,222,128,0.25)", color: "var(--gate-green)",  label: "안전",  icon: "✅" },
    WARNING: { bg: "rgba(250,204,21,0.08)",  border: "rgba(250,204,21,0.25)",  color: "var(--gate-yellow)", label: "주의",  icon: "⚠️" },
    DANGER:  { bg: "rgba(248,113,113,0.08)", border: "rgba(248,113,113,0.25)", color: "var(--gate-red)",    label: "위험",  icon: "🚨" },
};

// 플래그 이름 → 한글 라벨 매핑
const FLAG_LABELS: Record<string, string> = {
    sp500_drop:    "S&P500 (SPY)",
    vix_spike:     "VIX 공포지수",
    ewy_drop:      "EWY 한국 ETF",
    exchange_rate: "원/달러 환율",
};

// ─── SeverityBanner: 전체 폭 심각도 배너 ───
function SeverityBanner({ result }: { result: OCFResult }) {
    const cfg = SEVERITY_CONFIG[result.severity];
    return (
        <div
            className="card p-5 md:p-6 fade-in"
            style={{
                background: cfg.bg,
                borderColor: cfg.border,
            }}
        >
            <div className="flex flex-col sm:flex-row sm:items-center gap-3">
                <div className="flex items-center gap-3">
                    <span className="text-3xl">{cfg.icon}</span>
                    <div>
                        <p className="text-xs font-medium" style={{ color: "var(--text-muted)" }}>
                            오버나이트 리스크 — {result.date}
                        </p>
                        <p className="text-2xl font-bold mt-0.5" style={{ color: cfg.color }}>
                            {cfg.label}
                        </p>
                    </div>
                </div>
                <p
                    className="sm:ml-auto text-sm leading-relaxed max-w-md"
                    style={{ color: "var(--text-secondary)" }}
                >
                    {result.summary}
                </p>
            </div>
        </div>
    );
}

// ─── MetricCard: 지표 1개 카드 ───
function MetricCard({ flag }: { flag: OCFFlag }) {
    const label = FLAG_LABELS[flag.name] ?? flag.name;
    const triggered = flag.triggered;

    return (
        <div
            className="card p-4 flex flex-col gap-3 fade-in"
            style={{
                borderColor: triggered ? "rgba(248,113,113,0.3)" : "var(--border-subtle)",
                background: triggered ? "rgba(248,113,113,0.04)" : "var(--bg-surface)",
            }}
        >
            <div className="flex items-center justify-between">
                <p className="text-xs font-medium" style={{ color: "var(--text-muted)" }}>
                    {label}
                </p>
                <span
                    className="w-2.5 h-2.5 rounded-full shrink-0"
                    style={{
                        background: triggered ? "var(--gate-red)" : "var(--gate-green)",
                        boxShadow: triggered
                            ? "0 0 8px rgba(248,113,113,0.5)"
                            : "0 0 8px rgba(74,222,128,0.4)",
                    }}
                />
            </div>

            <div>
                <p
                    className="text-2xl font-bold tabular-nums"
                    style={{ color: triggered ? "var(--gate-red)" : "var(--text-primary)" }}
                >
                    {typeof flag.value === "number"
                        ? flag.name === "exchange_rate"
                            ? flag.value.toLocaleString()
                            : flag.value > 0
                                ? `+${flag.value.toFixed(2)}%`
                                : `${flag.value.toFixed(2)}%`
                        : flag.value}
                </p>
                <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
                    임계값:{" "}
                    {flag.name === "exchange_rate"
                        ? flag.threshold.toLocaleString()
                        : `${flag.threshold > 0 ? "+" : ""}${flag.threshold}%`}
                </p>
            </div>

            <div
                className="text-xs px-2 py-1 rounded-md leading-relaxed"
                style={{
                    background: "rgba(255,255,255,0.04)",
                    color: "var(--text-secondary)",
                }}
            >
                {triggered ? "🔴 " : "🟢 "}
                {flag.message}
            </div>
        </div>
    );
}

// ─── FlagRow: 요약 행 ───
function FlagRow({ flag }: { flag: OCFFlag }) {
    const label = FLAG_LABELS[flag.name] ?? flag.name;
    return (
        <div
            className="flex items-center gap-3 px-4 py-3 rounded-lg"
            style={{
                background: flag.triggered
                    ? "rgba(248,113,113,0.06)"
                    : "rgba(255,255,255,0.02)",
            }}
        >
            <span
                className="w-2 h-2 rounded-full shrink-0"
                style={{ background: flag.triggered ? "var(--gate-red)" : "var(--gate-green)" }}
            />
            <p className="text-sm font-medium text-white w-28 shrink-0">{label}</p>
            <p className="text-xs flex-1" style={{ color: "var(--text-secondary)" }}>
                {flag.message}
            </p>
            <span
                className="text-xs font-medium tabular-nums shrink-0"
                style={{ color: flag.triggered ? "var(--gate-red)" : "var(--gate-green)" }}
            >
                {flag.triggered ? "발동" : "정상"}
            </span>
        </div>
    );
}

// ─── 스켈레톤 ───
function SkeletonOCF() {
    return (
        <div className="flex flex-col gap-5">
            <div className="skeleton h-24 rounded-xl" />
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                {Array.from({ length: 4 }).map((_, i) => (
                    <div key={i} className="skeleton h-32 rounded-xl" />
                ))}
            </div>
            <div className="space-y-2">
                {Array.from({ length: 4 }).map((_, i) => (
                    <div key={i} className="skeleton h-10 rounded-lg" />
                ))}
            </div>
        </div>
    );
}

// ─── 메인 페이지 ───
export default function OCFPage() {
    const [result, setResult] = useState<OCFResult | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

    const fetchData = useCallback(async () => {
        try {
            const data = await ocfAPI.getLatest();
            setResult(data);
            setLastUpdated(new Date());
            setError(null);
        } catch (e) {
            setError((e as Error).message);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchData();
        const timer = setInterval(fetchData, 60_000);
        return () => clearInterval(timer);
    }, [fetchData]);

    return (
        <div className="flex-1 p-6 pb-20 md:pb-6 fade-in">
            {/* 헤더 */}
            <div className="flex flex-wrap items-center justify-between gap-3 mb-6">
                <div>
                    <h1 className="text-xl font-bold text-white">야간 리스크 (OCF)</h1>
                    <p className="text-sm mt-0.5" style={{ color: "var(--text-muted)" }}>
                        미국장 선행 지표 — 매일 08:30 업데이트
                    </p>
                </div>
                <div className="flex items-center gap-3">
                    {lastUpdated && (
                        <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                            갱신: {lastUpdated.toLocaleTimeString("ko-KR")}
                        </p>
                    )}
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
            </div>

            {/* 에러 */}
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
                <SkeletonOCF />
            ) : !result ? (
                <div className="card p-12 text-center">
                    <p className="text-4xl mb-3">🌙</p>
                    <p className="font-medium text-white">OCF 데이터 없음</p>
                    <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>
                        매일 08:30 이후 업데이트됩니다.
                    </p>
                </div>
            ) : (
                <div className="flex flex-col gap-5">
                    {/* 심각도 배너 */}
                    <SeverityBanner result={result} />

                    {/* 4개 지표 카드 */}
                    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                        {result.flags.map((flag) => (
                            <MetricCard key={flag.name} flag={flag} />
                        ))}
                    </div>

                    {/* 플래그 메시지 목록 */}
                    <div className="card overflow-hidden">
                        <div
                            className="px-4 py-3 border-b"
                            style={{ borderColor: "var(--border-subtle)" }}
                        >
                            <p className="text-sm font-medium text-white">플래그 상세</p>
                        </div>
                        <div className="p-3 flex flex-col gap-1.5">
                            {result.flags.map((flag) => (
                                <FlagRow key={flag.name} flag={flag} />
                            ))}
                        </div>
                    </div>

                    {/* 마지막 업데이트 */}
                    <p className="text-xs text-center" style={{ color: "var(--text-muted)" }}>
                        데이터 기준일: {result.date} · 60초마다 자동 갱신
                    </p>
                </div>
            )}
        </div>
    );
}
