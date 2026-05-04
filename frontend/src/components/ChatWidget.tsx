'use client';

/**
 * ChatWidget - 우측 하단 플로팅 AI 챗봇 (ChatWidget.tsx)
 *
 * 설계 의도:
 * - 플로팅 버튼으로 어느 페이지에서도 바로 챗봇 접근 가능
 * - 세션 ID를 유지해 대화 컨텍스트를 Flask 챗봇 모듈에 전달
 */

import { useState, useRef, useEffect } from 'react';
import { chatbotAPI } from '@/lib/api';

interface Message {
    id: number;
    role: 'user' | 'bot';
    text: string;
    loading?: boolean;
}

function MessageBubble({ msg }: { msg: Message }) {
    const isUser = msg.role === 'user';
    return (
        <div className={`flex gap-2 ${isUser ? 'justify-end' : 'justify-start'}`}>
            {!isUser && (
                <div
                    className="w-7 h-7 rounded-full flex items-center justify-center text-sm shrink-0 mt-0.5"
                    style={{ background: 'rgba(99,102,241,0.2)' }}
                >
                    🤖
                </div>
            )}
            <div
                className="max-w-[78%] px-3 py-2 rounded-2xl text-sm leading-relaxed"
                style={{
                    background: isUser ? 'rgba(99,102,241,0.3)' : 'rgba(255,255,255,0.07)',
                    color: 'var(--text-primary)',
                    borderTopRightRadius: isUser ? '4px' : undefined,
                    borderTopLeftRadius: !isUser ? '4px' : undefined,
                }}
            >
                {msg.loading ? (
                    <span className="inline-flex gap-1 items-center">
                        <span className="w-1.5 h-1.5 rounded-full bg-white/40 animate-bounce" style={{ animationDelay: '0ms' }} />
                        <span className="w-1.5 h-1.5 rounded-full bg-white/40 animate-bounce" style={{ animationDelay: '150ms' }} />
                        <span className="w-1.5 h-1.5 rounded-full bg-white/40 animate-bounce" style={{ animationDelay: '300ms' }} />
                    </span>
                ) : (
                    msg.text.split('\n').map((line, i, arr) => (
                        <span key={i}>
                            {line}
                            {i < arr.length - 1 && <br />}
                        </span>
                    ))
                )}
            </div>
        </div>
    );
}

export default function ChatWidget() {
    const [open, setOpen] = useState(false);
    const [messages, setMessages] = useState<Message[]>([
        {
            id: 0,
            role: 'bot',
            text: '안녕하세요! 종가봇입니다 🤖\n시장 현황, 종목 분석, VCP 시그널에 대해 질문해주세요.',
        },
    ]);
    const [input, setInput] = useState('');
    const [sending, setSending] = useState(false);
    const sessionId = useRef(`session_${Date.now()}`);
    const bottomRef = useRef<HTMLDivElement>(null);
    const inputRef = useRef<HTMLInputElement>(null);

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    useEffect(() => {
        if (open) setTimeout(() => inputRef.current?.focus(), 100);
    }, [open]);

    const sendMessage = async () => {
        const text = input.trim();
        if (!text || sending) return;

        const userMsg: Message = { id: Date.now(), role: 'user', text };
        const loadingId = Date.now() + 1;
        const loadingMsg: Message = { id: loadingId, role: 'bot', text: '', loading: true };

        setMessages((prev) => [...prev, userMsg, loadingMsg]);
        setInput('');
        setSending(true);

        try {
            const res = await chatbotAPI.send(text, sessionId.current);
            setMessages((prev) =>
                prev.map((m) => (m.id === loadingId ? { ...m, text: res.response, loading: false } : m))
            );
        } catch {
            setMessages((prev) =>
                prev.map((m) =>
                    m.id === loadingId
                        ? { ...m, text: '⚠️ 응답 실패. Flask 서버가 실행 중인지 확인하세요.', loading: false }
                        : m
                )
            );
        } finally {
            setSending(false);
        }
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            void sendMessage();
        }
    };

    return (
        <>
            {/* ─── 채팅 모달 ─── */}
            {open && (
                <div
                    className="fixed bottom-20 right-4 md:bottom-6 md:right-6 z-50 flex flex-col"
                    style={{
                        width: 'min(360px, calc(100vw - 32px))',
                        height: '480px',
                        background: 'var(--bg-surface)',
                        border: '1px solid var(--border-subtle)',
                        borderRadius: '16px',
                        boxShadow: '0 8px 40px rgba(0,0,0,0.6)',
                    }}
                >
                    {/* 헤더 */}
                    <div
                        className="flex items-center justify-between px-4 py-3 border-b shrink-0"
                        style={{ borderColor: 'var(--border-subtle)' }}
                    >
                        <div className="flex items-center gap-2">
                            <span className="text-lg">🤖</span>
                            <div>
                                <p className="text-sm font-semibold text-white leading-none">종가봇</p>
                                <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
                                    AI 주식 어시스턴트
                                </p>
                            </div>
                        </div>
                        <button
                            onClick={() => setOpen(false)}
                            className="text-xl leading-none transition-opacity hover:opacity-60"
                            style={{ color: 'var(--text-muted)' }}
                        >
                            ✕
                        </button>
                    </div>

                    {/* 메시지 목록 */}
                    <div className="flex-1 overflow-y-auto p-4 space-y-3">
                        {messages.map((msg) => <MessageBubble key={msg.id} msg={msg} />)}
                        <div ref={bottomRef} />
                    </div>

                    {/* 입력창 */}
                    <div
                        className="flex items-center gap-2 px-3 py-3 border-t shrink-0"
                        style={{ borderColor: 'var(--border-subtle)' }}
                    >
                        <input
                            ref={inputRef}
                            type="text"
                            value={input}
                            onChange={(e) => setInput(e.target.value)}
                            onKeyDown={handleKeyDown}
                            placeholder="메시지 입력... (Enter 전송)"
                            disabled={sending}
                            className="flex-1 text-sm outline-none"
                            style={{
                                color: 'var(--text-primary)',
                                background: 'transparent',
                                padding: '6px 10px',
                                borderRadius: '8px',
                                border: '1px solid var(--border-subtle)',
                            }}
                        />
                        <button
                            onClick={sendMessage}
                            disabled={!input.trim() || sending}
                            className="w-8 h-8 rounded-lg flex items-center justify-center transition-all shrink-0 text-base font-bold"
                            style={{
                                background: input.trim() && !sending ? 'rgba(99,102,241,0.4)' : 'rgba(255,255,255,0.05)',
                                color: input.trim() && !sending ? '#a5b4fc' : 'var(--text-muted)',
                            }}
                        >
                            ↑
                        </button>
                    </div>
                </div>
            )}

            {/* ─── 플로팅 버튼 ─── */}
            <button
                onClick={() => setOpen((v) => !v)}
                className="fixed bottom-20 right-4 md:bottom-6 md:right-6 z-40 w-12 h-12 rounded-full flex items-center justify-center transition-all duration-200 shadow-lg"
                style={{
                    background: open ? 'rgba(99,102,241,0.5)' : 'rgba(99,102,241,0.25)',
                    border: '1px solid rgba(99,102,241,0.4)',
                    opacity: open ? 0 : 1,
                    pointerEvents: open ? 'none' : 'auto',
                    transform: open ? 'scale(0.8)' : 'scale(1)',
                }}
                aria-label="AI 챗봇 열기"
            >
                <span className="text-xl">🤖</span>
            </button>
        </>
    );
}
