"use client";

/**
 * 대시보드 레이아웃 - 사이드바 내비게이션 (dashboard/layout.tsx)
 *
 * 설계 의도:
 * - usePathname으로 현재 경로를 감지해 활성 메뉴를 하이라이트
 * - 모바일: 하단 탭바, 데스크탑: 좌측 사이드바
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import ChatWidget from "@/components/ChatWidget";

const NAV_ITEMS = [
    {
        href: "/dashboard/kr",
        label: "KR 오버뷰",
        icon: "📊",
        description: "마켓 게이트 & 섹터",
    },
    {
        href: "/dashboard/kr/vcp",
        label: "VCP 시그널",
        icon: "📡",
        description: "수급 + VCP 패턴",
    },
    {
        href: "/dashboard/kr/closing-bet",
        label: "종가베팅 V2",
        icon: "⚡",
        description: "AI 채점 시그널",
    },
];

export default function DashboardLayout({
    children,
}: {
    children: React.ReactNode;
}) {
    const pathname = usePathname();

    return (
        <div className="flex min-h-screen" style={{ background: "var(--bg-page)" }}>
            {/* ─── 사이드바 (데스크탑) ─── */}
            <aside
                className="hidden md:flex flex-col w-56 shrink-0 border-r"
                style={{
                    background: "var(--bg-surface)",
                    borderColor: "var(--border-subtle)",
                }}
            >
                {/* 브랜드 */}
                <div
                    className="flex items-center gap-2 px-5 py-5 border-b"
                    style={{ borderColor: "var(--border-subtle)" }}
                >
                    <span className="text-2xl">⚡</span>
                    <div>
                        <p className="text-sm font-bold text-white leading-none">종가봇</p>
                        <p className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
                            대시보드
                        </p>
                    </div>
                </div>

                {/* 내비게이션 */}
                <nav className="flex flex-col gap-1 p-3 flex-1">
                    {NAV_ITEMS.map((item) => {
                        const isActive =
                            item.href === "/dashboard/kr"
                                ? pathname === "/dashboard/kr"
                                : pathname.startsWith(item.href);

                        return (
                            <Link
                                key={item.href}
                                href={item.href}
                                className="flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-150"
                                style={{
                                    background: isActive
                                        ? "rgba(255,255,255,0.08)"
                                        : "transparent",
                                    color: isActive ? "var(--text-primary)" : "var(--text-secondary)",
                                }}
                            >
                                <span className="text-lg">{item.icon}</span>
                                <div>
                                    <p className="text-sm font-medium leading-none">{item.label}</p>
                                    <p
                                        className="text-xs mt-0.5 leading-none"
                                        style={{ color: "var(--text-muted)" }}
                                    >
                                        {item.description}
                                    </p>
                                </div>
                                {isActive && (
                                    <div
                                        className="ml-auto w-1.5 h-1.5 rounded-full"
                                        style={{ background: "var(--gate-green)" }}
                                    />
                                )}
                            </Link>
                        );
                    })}
                </nav>

                {/* 하단 버전 */}
                <div
                    className="px-5 py-4 border-t"
                    style={{ borderColor: "var(--border-subtle)" }}
                >
                    <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                        Closing Bet v2.0
                    </p>
                </div>
            </aside>

            {/* ─── 메인 콘텐츠 ─── */}
            <main className="flex-1 flex flex-col min-w-0">
                {children}
            </main>

            {/* ─── 하단 탭바 (모바일) ─── */}
            <nav
                className="md:hidden fixed bottom-0 left-0 right-0 flex border-t z-50"
                style={{
                    background: "var(--bg-surface)",
                    borderColor: "var(--border-subtle)",
                }}
            >
                {NAV_ITEMS.map((item) => {
                    const isActive =
                        item.href === "/dashboard/kr"
                            ? pathname === "/dashboard/kr"
                            : pathname.startsWith(item.href);

                    return (
                        <Link
                            key={item.href}
                            href={item.href}
                            className="flex-1 flex flex-col items-center gap-1 py-3 transition-colors"
                            style={{ color: isActive ? "var(--text-primary)" : "var(--text-muted)" }}
                        >
                            <span className="text-xl">{item.icon}</span>
                            <span className="text-[10px]">{item.label}</span>
                        </Link>
                    );
                })}
            </nav>

            {/* ─── AI 챗봇 위젯 ─── */}
            <ChatWidget />
        </div>
    );
}
