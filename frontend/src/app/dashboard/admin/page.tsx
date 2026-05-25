"use client";

/**
 * 관리자 패널 (dashboard/admin/page.tsx)
 * 스케줄러 잡 상태 확인 + 수동 실행
 */

import { useEffect, useState, useCallback } from "react";
import { adminAPI, type AdminStatus, type OCFResult } from "@/lib/api";

const JOB_META: Record<string, { label: string; schedule: string }> = {
    ocf:      { label: "OCF 오버나이트 체크", schedule: "08:30" },
    update:   { label: "데이터 업데이트",     schedule: "08:50" },
    vcp:      { label: "VCP 스캔",            schedule: "14:50" },
    tracking: { label: "시그널 추적",          schedule: "14:55" },
    summary:  { label: "일일 요약 발송",       schedule: "15:00" },
};

const SEVERITY_STYLE = {
    OK:      { color: "var(--gate-green)",  bg: "rgba(74,222,128,0.08)",  label: "정상" },
    WARNING: { color: "var(--gate-yellow)", bg: "rgba(250,204,21,0.08)",  label: "주의" },
    DANGER:  { color: "var(--gate-red)",    bg: "rgba(248,113,113,0.08)", label: "위험" },
};

function Skeleton({ className }: { className?: string }) {
    return <div className={`skeleton ${className ?? ""}`} />;
}

function OCFStatusCard({ ocf }: { ocf: OCFResult }) {
    const cfg = SEVERITY_STYLE[ocf.severity] ?? SEVERITY_STYLE.OK;
    return (
        <div className="card p-4" style={{ background: cfg.bg, borderColor: cfg.color }}>
            <div className="flex items-center justify-between mb-3">
                <p className="text-sm font-semibold text-white">OCF 최신 결과</p>
                <span
                    className="text-xs font-bold px-2 py-0.5 rounded-full"
                    style={{ color: cfg.color, border: `1px solid ${cfg.color}` }}
                >
                    {ocf.severity} — {cfg.label}
                </span>
            </div>
            <p className="text-xs mb-3" style={{ color: "var(--text-secondary)" }}>{ocf.summary}</p>
            <div className="space-y-1.5">
                {ocf.flags.map((f) => (
                    <div key={f.name} className="flex items-center gap-2 text-xs">
                        <span
                            className="w-2 h-2 rounded-full shrink-0"
                            style={{ background: f.triggered ? "var(--gate-red)" : "var(--gate-green)" }}
                        />
                        <span style={{ color: "var(--text-secondary)" }}>{f.message}</span>
                    </div>
                ))}
            </div>
            <p className="text-xs mt-2" style={{ color: "var(--text-muted)" }}>날짜: {ocf.date}</p>
        </div>
    );
}

function JobRow({
    jobId,
    label,
    schedule,
}: {
    jobId: string;
    label: string;
    schedule: string;
}) {
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState<string | null>(null);

    const handleTrigger = async () => {
        setLoading(true);
        setResult(null);
        try {
            const res = await adminAPI.trigger(jobId);
            setResult(res.success ? "실행 완료" : "실행 실패");
        } catch {
            setResult("오류 발생");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div
            className="flex items-center justify-between p-3 rounded-lg"
            style={{ background: "rgba(255,255,255,0.03)", border: "1px solid var(--border-subtle)" }}
        >
            <div className="flex items-center gap-3 min-w-0">
                <div
                    className="w-10 h-10 rounded-lg flex items-center justify-center text-xs font-mono shrink-0"
                    style={{ background: "rgba(255,255,255,0.06)", color: "var(--text-muted)" }}
                >
                    {schedule}
                </div>
                <div className="min-w-0">
                    <p className="text-sm font-medium text-white truncate">{label}</p>
                    {result && (
                        <p className="text-xs mt-0.5" style={{ color: result.includes("완료") ? "var(--gate-green)" : "var(--gate-red)" }}>
                            {result}
                        </p>
                    )}
                </div>
            </div>
            <button
                onClick={handleTrigger}
                disabled={loading}
                className="ml-3 px-3 py-1.5 text-xs font-medium rounded-lg shrink-0 transition-all"
                style={{
                    background: loading ? "rgba(255,255,255,0.04)" : "rgba(99,102,241,0.15)",
                    color: loading ? "var(--text-muted)" : "#818cf8",
                    border: "1px solid rgba(99,102,241,0.3)",
                }}
            >
                {loading ? "실행 중..." : "▶ 실행"}
            </button>
        </div>
    );
}

function FreshnessRow({ label, value }: { label: string; value: string }) {
    const isMissing = value === "없음";
    return (
        <div className="flex items-center justify-between py-1.5 text-xs">
            <span style={{ color: "var(--text-muted)" }}>{label}</span>
            <span style={{ color: isMissing ? "var(--gate-red)" : "var(--text-secondary)" }}>
                {value}
            </span>
        </div>
    );
}

export default function AdminPage() {
    const [status, setStatus] = useState<AdminStatus | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const fetchStatus = useCallback(async () => {
        try {
            const data = await adminAPI.getStatus();
            setStatus(data);
            setError(null);
        } catch (e) {
            setError((e as Error).message);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchStatus();
        const interval = setInterval(fetchStatus, 60_000);
        return () => clearInterval(interval);
    }, [fetchStatus]);

    return (
        <div className="flex-1 p-6 pb-20 md:pb-6 fade-in">
            {/* 헤더 */}
            <div className="flex items-center justify-between mb-6">
                <div>
                    <h1 className="text-xl font-bold text-white">관리자 패널</h1>
                    <p className="text-sm mt-0.5" style={{ color: "var(--text-muted)" }}>
                        스케줄러 상태 & 수동 실행
                    </p>
                </div>
                <button
                    onClick={fetchStatus}
                    className="text-xs px-3 py-1.5 rounded-lg transition-colors"
                    style={{ background: "rgba(255,255,255,0.06)", color: "var(--text-secondary)" }}
                >
                    새로고침
                </button>
            </div>

            {error && (
                <div className="card p-4 mb-4 border-rose-500/30 bg-rose-500/10">
                    <p className="text-sm text-rose-400">⚠️ {error}</p>
                </div>
            )}

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* 스케줄러 잡 목록 */}
                <div className="lg:col-span-2 space-y-6">
                    <div>
                        <p className="text-sm font-semibold text-white mb-3">스케줄러 잡 (KST)</p>
                        <div className="space-y-2">
                            {loading
                                ? Array.from({ length: 5 }).map((_, i) => (
                                    <Skeleton key={i} className="h-14 rounded-lg" />
                                ))
                                : Object.entries(JOB_META).map(([id, meta]) => (
                                    <JobRow key={id} jobId={id} label={meta.label} schedule={meta.schedule} />
                                ))}
                        </div>
                    </div>

                    {/* 데이터 신선도 */}
                    {status && (
                        <div className="card p-4">
                            <p className="text-sm font-semibold text-white mb-2">데이터 신선도</p>
                            <div className="divide-y" style={{ borderColor: "var(--border-subtle)" }}>
                                {Object.entries(status.data_freshness).map(([k, v]) => (
                                    <FreshnessRow key={k} label={k} value={v} />
                                ))}
                            </div>
                        </div>
                    )}
                </div>

                {/* OCF 최신 결과 */}
                <div>
                    <p className="text-sm font-semibold text-white mb-3">OCF 최신 결과</p>
                    {loading ? (
                        <Skeleton className="h-48 rounded-xl" />
                    ) : status?.ocf_latest ? (
                        <OCFStatusCard ocf={status.ocf_latest} />
                    ) : (
                        <div className="card p-6 text-center">
                            <p className="text-4xl mb-2">🌙</p>
                            <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                                OCF 데이터 없음
                            </p>
                            <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
                                매일 08:30 KST 업데이트
                            </p>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
