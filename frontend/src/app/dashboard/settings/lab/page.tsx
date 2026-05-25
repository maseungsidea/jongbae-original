"use client";

/**
 * 파라미터 실험실 화면 (dashboard/settings/lab/page.tsx)
 *
 * 설계 의도:
 * - OCF 필터 임계값을 슬라이더로 실시간 조정
 * - 3열 비교표로 "베이스라인 vs OCF WARNING 스킵 vs OCF DANGER 스킵" 즉시 비교
 * - 개선 항목은 초록으로 하이라이트해 효과 즉시 파악
 * - 해석 텍스트로 의사결정 보조
 */

import { useEffect, useState, useCallback } from "react";
import { backtestAPI, type BacktestComparison, type BacktestStats } from "@/lib/api";

// ─── 파라미터 정의 ───
interface ParamDef {
    key: string;
    label: string;
    unit: string;
    min: number;
    max: number;
    step: number;
    default: number;
    description: string;
}

const PARAM_DEFS: ParamDef[] = [
    {
        key:         "spy_drop_threshold",
        label:       "S&P500 낙폭 임계",
        unit:        "%",
        min:         -3.0,
        max:         -0.5,
        step:        0.1,
        default:     -1.5,
        description: "SPY 당일 하락이 이 값 이하이면 WARNING 발동",
    },
    {
        key:         "vix_threshold",
        label:       "VIX 공포 임계",
        unit:        "",
        min:         20,
        max:         35,
        step:        0.5,
        default:     25,
        description: "VIX 절대값이 이 값 이상이면 WARNING 발동",
    },
    {
        key:         "ewy_drop_threshold",
        label:       "EWY 낙폭 임계",
        unit:        "%",
        min:         -3.0,
        max:         -0.5,
        step:        0.1,
        default:     -1.0,
        description: "EWY(한국 ETF) 낙폭이 이 값 이하이면 WARNING 발동",
    },
    {
        key:         "usdkrw_threshold",
        label:       "원/달러 임계",
        unit:        "원",
        min:         1400,
        max:         1600,
        step:        10,
        default:     1450,
        description: "USD/KRW 환율이 이 값 이상이면 WARNING 발동",
    },
];

// ─── ParamSlider: 파라미터 1개 슬라이더 ───
function ParamSlider({
    def,
    value,
    onChange,
}: {
    def: ParamDef;
    value: number;
    onChange: (v: number) => void;
}) {
    // 음수 파라미터를 슬라이더로 표현하기 위해 절대값 사용
    const isNegative = def.min < 0;
    const sliderMin = isNegative ? Math.abs(def.max) : def.min;
    const sliderMax = isNegative ? Math.abs(def.min) : def.max;
    const sliderVal = isNegative ? Math.abs(value) : value;

    const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const raw = parseFloat(e.target.value);
        onChange(isNegative ? -raw : raw);
    };

    return (
        <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
                <div>
                    <p className="text-sm font-medium text-white">{def.label}</p>
                    <p className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
                        {def.description}
                    </p>
                </div>
                <div
                    className="text-sm font-bold tabular-nums px-3 py-1 rounded-lg shrink-0"
                    style={{
                        background: "rgba(129,140,248,0.1)",
                        color: "var(--grade-s)",
                        border: "1px solid rgba(129,140,248,0.2)",
                    }}
                >
                    {isNegative && value < 0 ? `−${Math.abs(value).toFixed(1)}` : value}
                    {def.unit}
                </div>
            </div>
            <div className="flex items-center gap-3">
                <span className="text-xs tabular-nums w-10 text-right" style={{ color: "var(--text-muted)" }}>
                    {isNegative ? `−${sliderMax}` : sliderMin}{def.unit}
                </span>
                <input
                    type="range"
                    min={sliderMin}
                    max={sliderMax}
                    step={def.step}
                    value={sliderVal}
                    onChange={handleChange}
                    className="flex-1 accent-indigo-400 h-1.5 rounded-full cursor-pointer"
                    style={{ accentColor: "var(--grade-s)" }}
                />
                <span className="text-xs tabular-nums w-10" style={{ color: "var(--text-muted)" }}>
                    {isNegative ? `−${sliderMin}` : sliderMax}{def.unit}
                </span>
            </div>
        </div>
    );
}

// ─── ComparisonTable: 3열 비교표 ───
function ComparisonTable({
    comparison,
}: {
    comparison: BacktestComparison;
}) {
    const columns: { key: keyof BacktestComparison; label: string; stats: BacktestStats }[] = [
        { key: "baseline",            label: "베이스라인",          stats: comparison.baseline },
        { key: "with_ocf_warning",    label: "OCF WARNING 스킵",    stats: comparison.with_ocf_warning },
        { key: "with_ocf_danger_only", label: "OCF DANGER 스킵",    stats: comparison.with_ocf_danger_only },
    ];

    const rows: { key: keyof BacktestStats; label: string; unit: string; higherIsBetter: boolean }[] = [
        { key: "trades",          label: "거래 수",      unit: "건",  higherIsBetter: false },
        { key: "ev_pct",          label: "평균 EV",      unit: "%",   higherIsBetter: true },
        { key: "wr",              label: "승률",          unit: "%",   higherIsBetter: true },
        { key: "mdd_pct",         label: "MDD",          unit: "%",   higherIsBetter: false },
        { key: "filter_rate",     label: "필터 제외율",  unit: "%",   higherIsBetter: false },
        { key: "filtered_trades", label: "제외 건수",    unit: "건",  higherIsBetter: false },
    ];

    const baseline = comparison.baseline;

    return (
        <div className="card overflow-hidden">
            <div
                className="px-4 py-3 border-b"
                style={{ borderColor: "var(--border-subtle)" }}
            >
                <p className="text-sm font-medium text-white">백테스트 결과 비교</p>
                <p className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
                    {comparison.label}
                </p>
            </div>
            <div className="overflow-x-auto">
                <table className="w-full">
                    <thead>
                        <tr style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                            <th
                                className="px-4 py-2.5 text-left text-xs font-medium"
                                style={{ color: "var(--text-muted)" }}
                            >
                                지표
                            </th>
                            {columns.map((col) => (
                                <th
                                    key={col.key}
                                    className="px-4 py-2.5 text-right text-xs font-medium"
                                    style={{ color: "var(--text-muted)" }}
                                >
                                    {col.label}
                                </th>
                            ))}
                        </tr>
                    </thead>
                    <tbody>
                        {rows.map((row) => (
                            <tr
                                key={row.key}
                                className="border-b"
                                style={{ borderColor: "var(--border-subtle)" }}
                            >
                                <td
                                    className="px-4 py-2.5 text-xs"
                                    style={{ color: "var(--text-secondary)" }}
                                >
                                    {row.label}
                                </td>
                                {columns.map((col, ci) => {
                                    const val = col.stats[row.key];
                                    if (val == null) {
                                        return (
                                            <td
                                                key={col.key}
                                                className="px-4 py-2.5 text-xs text-right tabular-nums"
                                                style={{ color: "var(--text-muted)" }}
                                            >
                                                —
                                            </td>
                                        );
                                    }

                                    const baseVal = baseline[row.key] as number;
                                    const isImproved =
                                        ci > 0 &&
                                        baseVal != null &&
                                        (row.higherIsBetter ? val > baseVal : val < baseVal);
                                    const isGoalMet =
                                        comparison.goal_met[`${col.key}_${row.key}`] ?? false;

                                    let color = "var(--text-primary)";
                                    if (ci > 0 && isImproved) color = "var(--gate-green)";
                                    if (ci > 0 && !isImproved && val !== baseVal)
                                        color = "var(--gate-red)";

                                    const display =
                                        row.unit === "%"
                                            ? `${val >= 0 ? "" : ""}${val.toFixed(2)}%`
                                            : `${Math.round(val)}${row.unit}`;

                                    return (
                                        <td
                                            key={col.key}
                                            className="px-4 py-2.5 text-xs text-right font-medium tabular-nums"
                                            style={{ color }}
                                        >
                                            {display}
                                            {isGoalMet && (
                                                <span className="ml-1 text-[10px]">✅</span>
                                            )}
                                            {ci > 0 && isImproved && (
                                                <span className="ml-1 text-[10px]">↑</span>
                                            )}
                                        </td>
                                    );
                                })}
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}

// ─── InterpretationText: 해석 텍스트 ───
function InterpretationText({ comparison }: { comparison: BacktestComparison }) {
    const base = comparison.baseline;
    const warn = comparison.with_ocf_warning;
    const danger = comparison.with_ocf_danger_only;

    const evDeltaWarn = warn.ev_pct - base.ev_pct;
    const evDeltaDanger = danger.ev_pct - base.ev_pct;

    return (
        <div
            className="card p-4 flex flex-col gap-2"
            style={{
                background: "rgba(129,140,248,0.04)",
                borderColor: "rgba(129,140,248,0.15)",
            }}
        >
            <p className="text-xs font-medium" style={{ color: "var(--grade-s)" }}>
                해석 요약
            </p>
            <div className="space-y-1.5">
                <p className="text-xs leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                    {`OCF WARNING 이상 스킵 시 EV: ${base.ev_pct.toFixed(2)}% → ${warn.ev_pct.toFixed(2)}% (${evDeltaWarn >= 0 ? "+" : ""}${evDeltaWarn.toFixed(2)}%p)`}
                </p>
                <p className="text-xs leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                    {`OCF DANGER 스킵 시 EV: ${base.ev_pct.toFixed(2)}% → ${danger.ev_pct.toFixed(2)}% (${evDeltaDanger >= 0 ? "+" : ""}${evDeltaDanger.toFixed(2)}%p)`}
                </p>
                {Object.entries(comparison.ocf_flag_days).map(([flag, days]) => (
                    <p key={flag} className="text-xs" style={{ color: "var(--text-muted)" }}>
                        {flag}: {days}일 발동 (전체 기간 중)
                    </p>
                ))}
                <p
                    className="text-xs font-medium mt-2"
                    style={{
                        color: warn.ev_pct >= 2.0
                            ? "var(--gate-green)"
                            : warn.ev_pct >= 1.5
                                ? "var(--gate-yellow)"
                                : "var(--gate-red)",
                    }}
                >
                    {warn.ev_pct >= 2.0
                        ? "✅ OCF WARNING 스킵 시 EV 2% 목표 달성"
                        : warn.ev_pct >= 1.5
                            ? "⚠️ OCF WARNING 스킵 후에도 EV 2% 미달 — 추가 조정 필요"
                            : "🚨 현재 파라미터로는 EV 2% 목표 미달"}
                </p>
            </div>
        </div>
    );
}

// ─── 스켈레톤 ───
function SkeletonLab() {
    return (
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
            <div className="lg:col-span-2 flex flex-col gap-4">
                {Array.from({ length: 4 }).map((_, i) => (
                    <div key={i} className="skeleton h-16 rounded-xl" />
                ))}
            </div>
            <div className="lg:col-span-3">
                <div className="skeleton h-64 rounded-xl" />
            </div>
        </div>
    );
}

// ─── 메인 페이지 ───
export default function LabPage() {
    const [comparison, setComparison] = useState<BacktestComparison | null>(null);
    const [loading, setLoading] = useState(true);
    const [running, setRunning] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // 파라미터 상태 (기본값으로 초기화)
    const [params, setParams] = useState<Record<string, number>>(
        Object.fromEntries(PARAM_DEFS.map((d) => [d.key, d.default]))
    );

    const loadLatest = useCallback(async () => {
        try {
            setLoading(true);
            const data = await backtestAPI.getLatest();
            setComparison(data);
            setError(null);
        } catch (e) {
            setError((e as Error).message);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        loadLatest();
    }, [loadLatest]);

    const handleRun = async () => {
        if (running) return;
        setRunning(true);
        try {
            const data = await backtestAPI.run(params);
            setComparison(data);
            setError(null);
        } catch (e) {
            setError(`실행 실패: ${(e as Error).message}`);
        } finally {
            setRunning(false);
        }
    };

    const updateParam = (key: string, value: number) => {
        setParams((prev) => ({ ...prev, [key]: value }));
    };

    return (
        <div className="flex-1 p-6 pb-20 md:pb-6 fade-in">
            {/* 헤더 */}
            <div className="mb-6">
                <h1 className="text-xl font-bold text-white">파라미터 실험실</h1>
                <p className="text-sm mt-0.5" style={{ color: "var(--text-muted)" }}>
                    OCF 필터 임계값 조정 → 백테스트 결과 즉시 비교
                </p>
            </div>

            {error && (
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
                <SkeletonLab />
            ) : (
                <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
                    {/* ─── 왼쪽: 파라미터 슬라이더 패널 ─── */}
                    <div className="lg:col-span-2">
                        <div className="card p-5 flex flex-col gap-5">
                            <div className="flex items-center gap-2">
                                <span className="text-lg">🔬</span>
                                <p className="text-sm font-medium text-white">OCF 임계값 설정</p>
                            </div>

                            <div className="flex flex-col gap-5">
                                {PARAM_DEFS.map((def) => (
                                    <ParamSlider
                                        key={def.key}
                                        def={def}
                                        value={params[def.key]}
                                        onChange={(v) => updateParam(def.key, v)}
                                    />
                                ))}
                            </div>

                            <button
                                onClick={handleRun}
                                disabled={running}
                                className="w-full py-2.5 text-sm font-medium rounded-lg transition-all"
                                style={{
                                    background: running
                                        ? "rgba(255,255,255,0.04)"
                                        : "rgba(129,140,248,0.15)",
                                    color: running ? "var(--text-muted)" : "var(--grade-s)",
                                    border: "1px solid rgba(129,140,248,0.3)",
                                }}
                            >
                                {running ? "⏳ 백테스트 실행 중..." : "▶ 현재 설정으로 실행"}
                            </button>

                            {/* 기본값 리셋 */}
                            <button
                                onClick={() =>
                                    setParams(
                                        Object.fromEntries(PARAM_DEFS.map((d) => [d.key, d.default]))
                                    )
                                }
                                className="w-full py-2 text-xs rounded-lg transition-colors"
                                style={{
                                    background: "rgba(255,255,255,0.04)",
                                    color: "var(--text-muted)",
                                }}
                            >
                                기본값으로 초기화
                            </button>
                        </div>
                    </div>

                    {/* ─── 오른쪽: 비교 결과 ─── */}
                    <div className="lg:col-span-3 flex flex-col gap-4">
                        {running ? (
                            <div className="skeleton h-64 rounded-xl" />
                        ) : comparison ? (
                            <>
                                <ComparisonTable comparison={comparison} />
                                <InterpretationText comparison={comparison} />
                            </>
                        ) : (
                            <div className="card p-12 text-center">
                                <p className="text-4xl mb-3">📊</p>
                                <p className="font-medium text-white">결과 없음</p>
                                <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>
                                    파라미터 설정 후 실행 버튼을 눌러 백테스트를 시작하세요.
                                </p>
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}
