"use client";

/**
 * KR 마켓 오버뷰 페이지 (dashboard/kr/page.tsx)
 *
 * 설계 의도:
 * - Market Gate 원형 스코어로 매수 가능 여부를 직관적으로 표시
 * - 섹터별 ETF 신호 그리드로 시장 흐름 파악
 * - 60초마다 자동 갱신하여 실시간성 유지
 */

import { useEffect, useState, useCallback } from "react";
import { krAPI, type MarketGateResult, type SectorResult } from "@/lib/api";

// ─── Gate 색상 매핑 ───
const GATE_CONFIG = {
    GREEN: { color: "var(--gate-green)", label: "매수 적합", bg: "rgba(74, 222, 128, 0.1)" },
    YELLOW: { color: "var(--gate-yellow)", label: "중립 관망", bg: "rgba(250, 204, 21, 0.1)" },
    RED: { color: "var(--gate-red)", label: "매수 자제", bg: "rgba(248, 113, 113, 0.1)" },
};

// ─── 섹터 신호 배지 ───
function SectorSignalBadge({ signal }: { signal: string }) {
    const map = {
        bullish: { label: "강세", color: "var(--color-up)" },
        bearish: { label: "약세", color: "var(--color-down)" },
        neutral: { label: "중립", color: "var(--text-muted)" },
    };
    const cfg = map[signal as keyof typeof map] ?? map.neutral;
    return (
        <span className="text-xs font-medium" style={{ color: cfg.color }}>
            {cfg.label}
        </span>
    );
}

// ─── 섹터 카드 ───
function SectorCard({ sector }: { sector: SectorResult }) {
    const isUp = sector.change_1d > 0;
    return (
        <div className="card p-3 flex flex-col gap-2">
            <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-white">{sector.name}</span>
                <SectorSignalBadge signal={sector.signal} />
            </div>
            <div className="flex items-center justify-between">
                <span
                    className="text-lg font-bold"
                    style={{ color: isUp ? "var(--color-up)" : sector.change_1d < 0 ? "var(--color-down)" : "var(--text-muted)" }}
                >
                    {isUp ? "+" : ""}{sector.change_1d.toFixed(2)}%
                </span>
                <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                    점수 {sector.score}
                </span>
            </div>
        </div>
    );
}

// ─── Market Gate 원형 스코어 ───
function MarketGaugeCard({ data }: { data: MarketGateResult }) {
    const cfg = GATE_CONFIG[data.gate] ?? GATE_CONFIG.YELLOW;
    const radius = 54;
    const circumference = 2 * Math.PI * radius;
    const dash = (data.score / 100) * circumference;

    return (
        <div className="card p-6 flex flex-col items-center gap-4" style={{ background: cfg.bg }}>
            <p className="text-sm font-semibold" style={{ color: "var(--text-secondary)" }}>
                Market Gate
            </p>

            {/* SVG 원형 게이지 */}
            <div className="relative">
                <svg width="140" height="140" viewBox="0 0 140 140">
                    {/* 배경 원 */}
                    <circle cx="70" cy="70" r={radius} fill="none" strokeWidth="10"
                        stroke="rgba(255,255,255,0.06)" />
                    {/* 스코어 원 */}
                    <circle
                        cx="70" cy="70" r={radius}
                        fill="none" strokeWidth="10"
                        stroke={cfg.color}
                        strokeLinecap="round"
                        strokeDasharray={`${dash} ${circumference - dash}`}
                        strokeDashoffset={circumference / 4}
                        style={{ transition: "stroke-dasharray 0.8s ease" }}
                    />
                </svg>
                <div className="absolute inset-0 flex flex-col items-center justify-center">
                    <span className="text-3xl font-bold text-white">{data.score}</span>
                    <span className="text-xs" style={{ color: "var(--text-muted)" }}>/ 100</span>
                </div>
            </div>

            {/* 상태 배지 */}
            <div
                className="px-4 py-1.5 rounded-full text-sm font-bold"
                style={{ background: cfg.bg, color: cfg.color, border: `1px solid ${cfg.color}` }}
            >
                {data.gate} — {cfg.label}
            </div>

            {/* 근거 목록 */}
            {data.reasons.length > 0 && (
                <ul className="w-full space-y-1">
                    {data.reasons.slice(0, 3).map((r, i) => (
                        <li key={i} className="text-xs flex items-start gap-1.5" style={{ color: "var(--text-muted)" }}>
                            <span className="mt-0.5">•</span>
                            <span>{r}</span>
                        </li>
                    ))}
                </ul>
            )}
        </div>
    );
}

// ─── 스켈레톤 ───
function Skeleton({ className }: { className?: string }) {
    return <div className={`skeleton ${className ?? ""}`} />;
}

// ─── 메인 페이지 ───
export default function KRMarketOverview() {
    const [marketGate, setMarketGate] = useState<MarketGateResult | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

    const fetchData = useCallback(async () => {
        try {
            const gate = await krAPI.getMarketGate();
            setMarketGate(gate);
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
        // 60초 간격 자동 갱신
        const interval = setInterval(fetchData, 60_000);
        return () => clearInterval(interval);
    }, [fetchData]);

    return (
        <div className="flex-1 p-6 pb-20 md:pb-6 fade-in">
            {/* 헤더 */}
            <div className="flex items-center justify-between mb-6">
                <div>
                    <h1 className="text-xl font-bold text-white">KR 마켓 오버뷰</h1>
                    <p className="text-sm mt-0.5" style={{ color: "var(--text-muted)" }}>
                        KOSPI / KOSDAQ 시장 상태 분석
                    </p>
                </div>
                {lastUpdated && (
                    <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                        {lastUpdated.toLocaleTimeString("ko-KR")} 갱신
                    </span>
                )}
            </div>

            {/* 에러 */}
            {error && (
                <div className="card p-4 mb-6 border-rose-500/30 bg-rose-500/10">
                    <p className="text-sm text-rose-400">⚠️ {error}</p>
                    <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
                        Flask 서버가 실행 중인지 확인하세요 (python flask_app.py)
                    </p>
                </div>
            )}

            {/* Market Gate + 섹터 그리드 */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Market Gate 카드 */}
                <div className="lg:col-span-1">
                    {loading ? (
                        <div className="card p-6 flex flex-col items-center gap-4">
                            <Skeleton className="w-32 h-4" />
                            <Skeleton className="w-36 h-36 rounded-full" />
                            <Skeleton className="w-28 h-7 rounded-full" />
                        </div>
                    ) : marketGate ? (
                        <MarketGaugeCard data={marketGate} />
                    ) : null}
                </div>

                {/* 섹터 그리드 */}
                <div className="lg:col-span-2">
                    <p className="text-sm font-semibold text-white mb-3">섹터별 ETF 신호</p>
                    {loading ? (
                        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                            {Array.from({ length: 6 }).map((_, i) => (
                                <Skeleton key={i} className="h-20" />
                            ))}
                        </div>
                    ) : marketGate && marketGate.sectors.length > 0 ? (
                        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                            {marketGate.sectors.map((s) => (
                                <SectorCard key={s.name} sector={s} />
                            ))}
                        </div>
                    ) : (
                        <div className="card p-6 text-center">
                            <p style={{ color: "var(--text-muted)" }} className="text-sm">
                                섹터 데이터 없음
                            </p>
                        </div>
                    )}
                </div>
            </div>

            {/* 주요 지표 (metrics) */}
            {marketGate && Object.keys(marketGate.metrics).length > 0 && (
                <div className="mt-6">
                    <p className="text-sm font-semibold text-white mb-3">주요 기술 지표</p>
                    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3">
                        {Object.entries(marketGate.metrics).map(([key, val]) => (
                            <div key={key} className="card p-3 text-center">
                                <p className="text-xs mb-1" style={{ color: "var(--text-muted)" }}>{key}</p>
                                <p className="text-lg font-bold text-white">
                                    {typeof val === "number" ? val.toFixed(1) : val}
                                </p>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* 바로가기 카드 */}
            <div className="mt-6 grid grid-cols-1 sm:grid-cols-2 gap-4">
                <a
                    href="/dashboard/kr/vcp"
                    className="card p-4 flex items-center gap-4 hover:border-white/20 transition-colors cursor-pointer"
                >
                    <span className="text-3xl">📡</span>
                    <div>
                        <p className="font-semibold text-white">VCP 시그널</p>
                        <p className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
                            외인/기관 수급 + VCP 패턴 종목
                        </p>
                    </div>
                    <span className="ml-auto" style={{ color: "var(--text-muted)" }}>→</span>
                </a>
                <a
                    href="/dashboard/kr/closing-bet"
                    className="card p-4 flex items-center gap-4 hover:border-white/20 transition-colors cursor-pointer"
                >
                    <span className="text-3xl">⚡</span>
                    <div>
                        <p className="font-semibold text-white">종가베팅 V2</p>
                        <p className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
                            AI 12점 채점 시그널 카드
                        </p>
                    </div>
                    <span className="ml-auto" style={{ color: "var(--text-muted)" }}>→</span>
                </a>
            </div>
        </div>
    );
}
