import React, { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import {
    MessageSquare, Search, Send, Plus, Users, Building2, User as UserIcon,
    Hash, X, Activity,
} from 'lucide-react';
import toast from 'react-hot-toast';
import { apiClient } from '../api/client';
import { useAuth } from '../context/AuthContext';
import PageHeader from '../components/PageHeader';

// Build the WebSocket URL the same way the rest of the app talks to the API:
// strip the /api suffix (apiClient uses baseURL '/api') and switch the scheme.
function buildWsUrl(userId, role) {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const role_q = role ? `?role=${encodeURIComponent(role)}` : '';
    return `${proto}//${window.location.host}/ws/notifications/${userId}${role_q}`;
}

const KIND_ICON = {
    direct: UserIcon,
    group: Users,
    department: Building2,
};

export default function Messages() {
    const { user } = useAuth();
    const me = user?.user_id;

    const [conversations, setConversations] = useState([]);
    const [activeId, setActiveId] = useState(null);
    const [messages, setMessages] = useState([]);
    const [draft, setDraft] = useState('');
    const [loadingList, setLoadingList] = useState(true);
    const [sending, setSending] = useState(false);

    const [picker, setPicker] = useState(null); // 'direct' | 'group' | null
    const messagesEndRef = useRef(null);
    const wsRef = useRef(null);

    // ---------- data loaders ----------
    const fetchConversations = useCallback(async () => {
        try {
            const res = await apiClient.get('/messaging/conversations');
            setConversations(res.data || []);
        } catch {
            // Silent — common during cold-start (auth refreshing).
        } finally {
            setLoadingList(false);
        }
    }, []);

    const fetchMessages = useCallback(async (id) => {
        if (!id) return;
        try {
            const res = await apiClient.get(`/messaging/conversations/${id}/messages`);
            setMessages(res.data || []);
            // Mark as read after the panel renders the messages.
            await apiClient.post(`/messaging/conversations/${id}/read`).catch(() => {});
            // Optimistically zero the badge for this conversation.
            setConversations((prev) =>
                prev.map((c) => (c.conversation_id === id ? { ...c, unread_count: 0 } : c))
            );
        } catch {
            toast.error('Could not load messages.');
        }
    }, []);

    useEffect(() => { fetchConversations(); }, [fetchConversations]);
    useEffect(() => { fetchMessages(activeId); }, [activeId, fetchMessages]);

    // ---------- live updates via WebSocket ----------
    useEffect(() => {
        if (!me) return undefined;
        let socket;
        try {
            socket = new WebSocket(buildWsUrl(me, user?.role));
            wsRef.current = socket;
        } catch {
            return undefined;
        }

        socket.onmessage = (ev) => {
            let evt;
            try { evt = JSON.parse(ev.data); } catch { return; }
            if (evt.type === 'message:new' && evt.message) {
                const cid = evt.conversation_id;
                // If the user is looking at this conversation, append immediately
                // and mark read on the server.
                if (cid === activeId) {
                    setMessages((prev) => [...prev, evt.message]);
                    apiClient.post(`/messaging/conversations/${cid}/read`).catch(() => {});
                }
                // Refresh the sidebar so unread counts + last-message previews update.
                fetchConversations();
            } else if (evt.type === 'conversation:joined' || evt.type === 'conversation:left') {
                fetchConversations();
            }
        };
        socket.onerror = () => {};
        socket.onclose = () => {};

        return () => {
            try { socket.close(); } catch { /* noop */ }
        };
    }, [me, user?.role, activeId, fetchConversations]);

    // ---------- scroll to bottom on new messages ----------
    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages.length, activeId]);

    // ---------- send ----------
    const handleSend = async (e) => {
        e?.preventDefault?.();
        const body = draft.trim();
        if (!body || !activeId || sending) return;
        setSending(true);
        try {
            const res = await apiClient.post(
                `/messaging/conversations/${activeId}/messages`,
                { body }
            );
            setMessages((prev) => [...prev, res.data]);
            setDraft('');
            fetchConversations();
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Could not send.');
        } finally {
            setSending(false);
        }
    };

    const activeConv = useMemo(
        () => conversations.find((c) => c.conversation_id === activeId) || null,
        [conversations, activeId]
    );

    return (
        <div className="flex flex-col gap-4 h-[calc(100vh-6rem)]">
            <PageHeader
                eyebrow="Inbox"
                icon={MessageSquare}
                title="Messages"
                subtitle="Direct chats and group conversations across departments."
            />
            <div className="flex flex-1 min-h-0 gap-4 flex-col md:flex-row">
            {/* Sidebar — full width on mobile (stacks above thread), fixed-width on tablet+. */}
            <aside className={`md:w-80 shrink-0 flex flex-col bg-white dark:bg-ink-900 border border-ink-200/70 dark:border-ink-800 rounded-2xl overflow-hidden ${activeId ? 'hidden md:flex' : 'flex'}`}>
                <div className="px-4 py-3 border-b border-ink-100 dark:border-ink-800 flex items-center justify-between">
                    <div>
                        <h2 className="text-sm font-semibold text-ink-900 dark:text-white tracking-tight">Conversations</h2>
                        <p className="text-xs text-ink-500 mt-0.5">{conversations.length} total</p>
                    </div>
                    <div className="flex gap-1">
                        <button
                            onClick={() => setPicker('direct')}
                            title="New direct message"
                            className="p-1.5 rounded-lg text-ink-500 hover:text-brand-600 hover:bg-brand-50 dark:hover:bg-brand-900/20"
                        >
                            <UserIcon size={16} />
                        </button>
                        <button
                            onClick={() => setPicker('group')}
                            title="New group chat"
                            className="p-1.5 rounded-lg text-ink-500 hover:text-brand-600 hover:bg-brand-50 dark:hover:bg-brand-900/20"
                        >
                            <Plus size={16} />
                        </button>
                    </div>
                </div>

                <div className="flex-1 overflow-y-auto custom-scrollbar">
                    {loadingList ? (
                        <div className="p-6 text-center text-ink-400 text-sm">
                            <Activity className="animate-spin mx-auto mb-2" size={20} /> Loading…
                        </div>
                    ) : conversations.length === 0 ? (
                        <div className="p-6 text-center text-ink-400 text-sm">
                            <MessageSquare className="mx-auto mb-2 opacity-40" size={28} />
                            No conversations yet. Start one with the buttons above.
                        </div>
                    ) : (
                        <ul className="divide-y divide-ink-100 dark:divide-ink-800">
                            {conversations.map((c) => {
                                const Icon = KIND_ICON[c.kind] || Hash;
                                const active = c.conversation_id === activeId;
                                return (
                                    <li key={c.conversation_id}>
                                        <button
                                            onClick={() => setActiveId(c.conversation_id)}
                                            className={`w-full text-left px-4 py-3 flex gap-3 transition-colors ${
                                                active
                                                    ? 'bg-brand-50 dark:bg-brand-900/20'
                                                    : 'hover:bg-ink-50 dark:hover:bg-ink-800/50'
                                            }`}
                                        >
                                            <span className="shrink-0 w-9 h-9 rounded-xl bg-ink-100 dark:bg-ink-800 text-ink-600 dark:text-ink-300 flex items-center justify-center">
                                                <Icon size={16} />
                                            </span>
                                            <div className="flex-1 min-w-0">
                                                <div className="flex items-center justify-between gap-2">
                                                    <p className="text-sm font-semibold text-ink-900 dark:text-white truncate">{c.title}</p>
                                                    {c.unread_count > 0 && (
                                                        <span className="shrink-0 inline-flex items-center justify-center min-w-[20px] h-5 px-1.5 text-[10px] font-bold rounded-full bg-rose-500 text-white">
                                                            {c.unread_count > 99 ? '99+' : c.unread_count}
                                                        </span>
                                                    )}
                                                </div>
                                                {c.last_message?.body && (
                                                    <p className="text-xs text-ink-500 truncate mt-0.5">
                                                        {c.last_message.body}
                                                    </p>
                                                )}
                                                <p className="text-2xs text-ink-400 mt-1 uppercase tracking-wider font-semibold">
                                                    {c.kind === 'department' ? 'Department' : c.kind === 'group' ? 'Group' : 'Direct'}
                                                </p>
                                            </div>
                                        </button>
                                    </li>
                                );
                            })}
                        </ul>
                    )}
                </div>
            </aside>

            {/* Main panel */}
            <section className={`flex-1 flex flex-col bg-white dark:bg-ink-900 border border-ink-200/70 dark:border-ink-800 rounded-2xl overflow-hidden ${activeId ? 'flex' : 'hidden md:flex'}`}>
                {!activeConv ? (
                    <div className="flex-1 flex flex-col items-center justify-center text-ink-400 p-8">
                        <MessageSquare size={40} className="mb-3 opacity-40" aria-hidden="true" />
                        <p className="text-sm">Select a conversation, or start a new one.</p>
                    </div>
                ) : (
                    <>
                        <header className="px-5 py-3 border-b border-ink-100 dark:border-ink-800 flex items-center gap-3">
                            <button
                                type="button"
                                onClick={() => setActiveId(null)}
                                aria-label="Back to conversations"
                                className="md:hidden p-1.5 -ml-1.5 rounded-lg text-ink-500 hover:text-ink-900 hover:bg-ink-100 cursor-pointer"
                            >
                                <X size={18} aria-hidden="true" />
                            </button>
                            {(() => {
                                const Icon = KIND_ICON[activeConv.kind] || Hash;
                                return (
                                    <span className="shrink-0 w-9 h-9 rounded-xl bg-brand-50 dark:bg-brand-900/30 text-brand-600 flex items-center justify-center" aria-hidden="true">
                                        <Icon size={18} />
                                    </span>
                                );
                            })()}
                            <div className="min-w-0">
                                <h2 className="text-base font-semibold text-ink-900 dark:text-white truncate">
                                    {activeConv.title}
                                </h2>
                                <p className="text-xs text-ink-500 mt-0.5">
                                    {activeConv.kind === 'direct'
                                        ? 'Direct message'
                                        : `${activeConv.members.length} participants`}
                                </p>
                            </div>
                        </header>

                        <div className="flex-1 overflow-y-auto custom-scrollbar p-5 space-y-3 bg-ink-50/40 dark:bg-ink-950/40">
                            {messages.length === 0 ? (
                                <div className="text-center text-ink-400 text-sm py-12">
                                    <MessageSquare size={32} className="mx-auto mb-2 opacity-40" />
                                    No messages yet. Say hi.
                                </div>
                            ) : (
                                messages.map((m) => {
                                    const mine = m.sender_id === me;
                                    const sender = activeConv.members.find((u) => u.user_id === m.sender_id);
                                    return (
                                        <div key={m.message_id} className={`flex ${mine ? 'justify-end' : 'justify-start'}`}>
                                            <div className={`max-w-[70%] ${mine ? 'items-end' : 'items-start'} flex flex-col`}>
                                                {!mine && sender && (
                                                    <span className="text-2xs text-ink-500 font-semibold mb-0.5 px-1">
                                                        {sender.full_name}
                                                    </span>
                                                )}
                                                <div className={`rounded-2xl px-4 py-2 text-sm leading-relaxed whitespace-pre-wrap break-words ${
                                                    mine
                                                        ? 'bg-brand-600 text-white rounded-br-sm'
                                                        : 'bg-white dark:bg-ink-800 text-ink-900 dark:text-white border border-ink-100 dark:border-ink-700 rounded-bl-sm'
                                                }`}>
                                                    {m.body}
                                                </div>
                                                <span className="text-2xs text-ink-400 mt-1 px-1">
                                                    {new Date(m.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                                                </span>
                                            </div>
                                        </div>
                                    );
                                })
                            )}
                            <div ref={messagesEndRef} />
                        </div>

                        <form
                            onSubmit={handleSend}
                            className="border-t border-ink-100 dark:border-ink-800 p-3 flex gap-2"
                        >
                            <input
                                value={draft}
                                onChange={(e) => setDraft(e.target.value)}
                                placeholder="Type a message…"
                                className="flex-1 px-4 py-2.5 rounded-xl bg-ink-50 dark:bg-ink-800 text-sm text-ink-900 dark:text-white placeholder-ink-400 border border-transparent focus:border-brand-300 focus:bg-white dark:focus:bg-ink-900 outline-none transition-colors"
                                maxLength={4000}
                                disabled={sending}
                            />
                            <button
                                type="submit"
                                disabled={!draft.trim() || sending}
                                className="px-4 py-2.5 rounded-xl bg-brand-600 text-white text-sm font-semibold disabled:opacity-40 disabled:cursor-not-allowed hover:bg-brand-700 transition-colors flex items-center gap-2"
                            >
                                <Send size={16} /> Send
                            </button>
                        </form>
                    </>
                )}
            </section>
            </div>

            {picker && (
                <NewConversationModal
                    kind={picker}
                    onClose={() => setPicker(null)}
                    onCreated={(conv) => {
                        setPicker(null);
                        fetchConversations();
                        setActiveId(conv.conversation_id);
                    }}
                />
            )}
        </div>
    );
}


function NewConversationModal({ kind, onClose, onCreated }) {
    const [search, setSearch] = useState('');
    const [staff, setStaff] = useState([]);
    const [selected, setSelected] = useState([]);
    const [title, setTitle] = useState('');
    const [busy, setBusy] = useState(false);

    useEffect(() => {
        let cancelled = false;
        const t = setTimeout(async () => {
            try {
                const res = await apiClient.get('/messaging/staff', {
                    params: search ? { q: search } : {},
                });
                if (!cancelled) setStaff(res.data || []);
            } catch { /* noop */ }
        }, 200);
        return () => { cancelled = true; clearTimeout(t); };
    }, [search]);

    const toggle = (u) => {
        if (kind === 'direct') {
            setSelected([u]);
        } else {
            setSelected((prev) =>
                prev.find((p) => p.user_id === u.user_id)
                    ? prev.filter((p) => p.user_id !== u.user_id)
                    : [...prev, u]
            );
        }
    };

    const submit = async () => {
        if (busy) return;
        if (selected.length === 0) {
            toast.error('Pick at least one person.');
            return;
        }
        if (kind === 'group' && !title.trim()) {
            toast.error('Group needs a name.');
            return;
        }
        setBusy(true);
        try {
            let res;
            if (kind === 'direct') {
                res = await apiClient.post('/messaging/conversations/direct', {
                    user_id: selected[0].user_id,
                });
            } else {
                res = await apiClient.post('/messaging/conversations/group', {
                    title: title.trim(),
                    user_ids: selected.map((u) => u.user_id),
                });
            }
            onCreated(res.data);
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Could not create conversation.');
        } finally {
            setBusy(false);
        }
    };

    return (
        <div className="fixed inset-0 bg-ink-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="w-full max-w-lg bg-white dark:bg-ink-900 rounded-2xl shadow-elevated overflow-hidden">
                <div className="px-5 py-4 border-b border-ink-100 dark:border-ink-800 flex items-center justify-between">
                    <h3 className="text-sm font-semibold text-ink-900 dark:text-white">
                        {kind === 'direct' ? 'New direct message' : 'New group chat'}
                    </h3>
                    <button onClick={onClose} className="p-1 text-ink-400 hover:text-ink-700">
                        <X size={18} />
                    </button>
                </div>

                <div className="p-5 space-y-3">
                    {kind === 'group' && (
                        <input
                            value={title}
                            onChange={(e) => setTitle(e.target.value)}
                            placeholder="Group name (e.g. Cardiology Sync)"
                            className="w-full px-4 py-2.5 rounded-xl bg-ink-50 dark:bg-ink-800 text-sm border border-transparent focus:border-brand-300 outline-none"
                            maxLength={255}
                        />
                    )}

                    <div className="relative">
                        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-400" />
                        <input
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                            placeholder="Search staff by name or email"
                            className="w-full pl-9 pr-3 py-2.5 rounded-xl bg-ink-50 dark:bg-ink-800 text-sm border border-transparent focus:border-brand-300 outline-none"
                        />
                    </div>

                    {selected.length > 0 && (
                        <div className="flex flex-wrap gap-1.5">
                            {selected.map((u) => (
                                <span key={u.user_id} className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-brand-50 text-brand-700 text-xs font-semibold">
                                    {u.full_name}
                                    <button onClick={() => toggle(u)} className="hover:text-brand-900">
                                        <X size={12} />
                                    </button>
                                </span>
                            ))}
                        </div>
                    )}

                    <div className="max-h-72 overflow-y-auto custom-scrollbar border border-ink-100 dark:border-ink-800 rounded-xl">
                        {staff.length === 0 ? (
                            <div className="p-4 text-center text-ink-400 text-sm">No staff matched.</div>
                        ) : (
                            <ul className="divide-y divide-ink-100 dark:divide-ink-800">
                                {staff.map((u) => {
                                    const isSelected = !!selected.find((s) => s.user_id === u.user_id);
                                    return (
                                        <li key={u.user_id}>
                                            <button
                                                onClick={() => toggle(u)}
                                                className={`w-full text-left px-4 py-2.5 flex items-center gap-3 transition-colors ${
                                                    isSelected ? 'bg-brand-50 dark:bg-brand-900/20' : 'hover:bg-ink-50 dark:hover:bg-ink-800/50'
                                                }`}
                                            >
                                                <span className="shrink-0 w-8 h-8 rounded-full bg-ink-200 dark:bg-ink-700 text-ink-700 dark:text-ink-200 flex items-center justify-center font-semibold text-xs">
                                                    {u.full_name.charAt(0)}
                                                </span>
                                                <div className="flex-1 min-w-0">
                                                    <p className="text-sm font-semibold text-ink-900 dark:text-white truncate">{u.full_name}</p>
                                                    <p className="text-xs text-ink-500 truncate">{u.role || u.email}</p>
                                                </div>
                                            </button>
                                        </li>
                                    );
                                })}
                            </ul>
                        )}
                    </div>
                </div>

                <div className="px-5 py-3 border-t border-ink-100 dark:border-ink-800 flex justify-end gap-2 bg-ink-50/40 dark:bg-ink-950/40">
                    <button
                        onClick={onClose}
                        className="px-4 py-2 rounded-lg text-sm font-semibold text-ink-700 dark:text-ink-300 hover:bg-ink-100 dark:hover:bg-ink-800"
                    >
                        Cancel
                    </button>
                    <button
                        onClick={submit}
                        disabled={busy}
                        className="px-4 py-2 rounded-lg text-sm font-semibold bg-brand-600 text-white hover:bg-brand-700 disabled:opacity-40"
                    >
                        {busy ? 'Creating…' : 'Start conversation'}
                    </button>
                </div>
            </div>
        </div>
    );
}
