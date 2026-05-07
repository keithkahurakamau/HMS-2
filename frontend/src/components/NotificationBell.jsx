import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Bell, Check, CheckCheck, Info, AlertCircle, AlertTriangle, CheckCircle2 } from 'lucide-react';
import { apiClient } from '../api/client';

const POLL_INTERVAL_MS = 30_000;

const CATEGORY_ICONS = {
    info: Info,
    success: CheckCircle2,
    warning: AlertTriangle,
    critical: AlertCircle,
};

const CATEGORY_COLORS = {
    info: 'text-blue-500',
    success: 'text-emerald-500',
    warning: 'text-amber-500',
    critical: 'text-rose-500',
};

export default function NotificationBell() {
    const [open, setOpen] = useState(false);
    const [notifications, setNotifications] = useState([]);
    const [unreadCount, setUnreadCount] = useState(0);
    const dropdownRef = useRef(null);
    const navigate = useNavigate();

    const fetchNotifications = useCallback(async () => {
        try {
            const res = await apiClient.get('/notifications/');
            setNotifications(res.data.notifications || []);
            setUnreadCount(res.data.unread_count || 0);
        } catch (e) {
            // Silently ignore — user not authenticated yet, etc.
        }
    }, []);

    // Initial fetch + light polling. WebSocket fan-out covers the live case;
    // polling is a fallback in case the socket is closed or proxied away.
    useEffect(() => {
        fetchNotifications();
        const id = setInterval(fetchNotifications, POLL_INTERVAL_MS);
        return () => clearInterval(id);
    }, [fetchNotifications]);

    // Click-outside handler
    useEffect(() => {
        if (!open) return;
        const handler = (e) => {
            if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
                setOpen(false);
            }
        };
        document.addEventListener('mousedown', handler);
        return () => document.removeEventListener('mousedown', handler);
    }, [open]);

    const markRead = async (id) => {
        try {
            await apiClient.patch(`/notifications/${id}/read`);
            fetchNotifications();
        } catch {}
    };

    const markAllRead = async () => {
        try {
            await apiClient.patch('/notifications/read-all');
            fetchNotifications();
        } catch {}
    };

    const handleClick = (n) => {
        if (!n.is_read) markRead(n.notification_id);
        if (n.link) {
            navigate(n.link);
            setOpen(false);
        }
    };

    return (
        <div className="relative" ref={dropdownRef}>
            <button
                type="button"
                onClick={() => setOpen((v) => !v)}
                aria-label={`Notifications, ${unreadCount} unread`}
                aria-expanded={open}
                aria-haspopup="true"
                className="relative p-2 text-slate-500 hover:text-slate-800 dark:text-slate-300 dark:hover:text-white rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
            >
                <Bell size={20} aria-hidden="true" />
                {unreadCount > 0 && (
                    <span
                        className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] px-1 bg-rose-500 text-white text-[10px] font-black rounded-full flex items-center justify-center"
                        aria-hidden="true"
                    >
                        {unreadCount > 99 ? '99+' : unreadCount}
                    </span>
                )}
            </button>

            {open && (
                <div
                    role="dialog"
                    aria-label="Notification inbox"
                    className="absolute right-0 mt-2 w-96 max-w-[calc(100vw-2rem)] bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl shadow-2xl overflow-hidden z-50"
                >
                    <div className="px-4 py-3 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between bg-slate-50 dark:bg-slate-950/50">
                        <div>
                            <h3 className="font-bold text-slate-900 dark:text-white text-sm">Notifications</h3>
                            <p className="text-xs text-slate-500">{unreadCount > 0 ? `${unreadCount} unread` : 'All caught up'}</p>
                        </div>
                        {unreadCount > 0 && (
                            <button
                                onClick={markAllRead}
                                className="text-xs font-bold text-brand-600 hover:text-brand-700 flex items-center gap-1"
                            >
                                <CheckCheck size={14} /> Mark all read
                            </button>
                        )}
                    </div>

                    <div className="max-h-96 overflow-y-auto custom-scrollbar">
                        {notifications.length === 0 ? (
                            <div className="px-4 py-8 text-center text-slate-400 text-sm">
                                No notifications yet.
                            </div>
                        ) : (
                            <ul className="divide-y divide-slate-100 dark:divide-slate-800">
                                {notifications.map((n) => {
                                    const Icon = CATEGORY_ICONS[n.category] || Info;
                                    return (
                                        <li
                                            key={n.notification_id}
                                            className={`group ${!n.is_read ? 'bg-brand-50/40 dark:bg-brand-900/10' : ''}`}
                                        >
                                            <button
                                                onClick={() => handleClick(n)}
                                                className="w-full text-left px-4 py-3 hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors flex gap-3"
                                            >
                                                <Icon
                                                    size={18}
                                                    className={`shrink-0 mt-0.5 ${CATEGORY_COLORS[n.category] || 'text-slate-500'}`}
                                                    aria-hidden="true"
                                                />
                                                <div className="flex-1 min-w-0">
                                                    <div className="flex items-center gap-2">
                                                        <p className={`text-sm ${n.is_read ? 'text-slate-700 dark:text-slate-300' : 'font-bold text-slate-900 dark:text-white'} truncate`}>
                                                            {n.title}
                                                        </p>
                                                        {!n.is_read && (
                                                            <span
                                                                className="w-2 h-2 rounded-full bg-brand-500 shrink-0"
                                                                aria-label="Unread"
                                                            />
                                                        )}
                                                    </div>
                                                    {n.body && (
                                                        <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5 line-clamp-2">
                                                            {n.body}
                                                        </p>
                                                    )}
                                                    <p className="text-[10px] text-slate-400 dark:text-slate-500 mt-1 uppercase tracking-wider font-bold">
                                                        {new Date(n.created_at).toLocaleString()}
                                                    </p>
                                                </div>
                                                {!n.is_read && (
                                                    <span
                                                        role="button"
                                                        tabIndex={0}
                                                        aria-label="Mark as read"
                                                        onClick={(e) => { e.stopPropagation(); markRead(n.notification_id); }}
                                                        onKeyDown={(e) => {
                                                            if (e.key === 'Enter' || e.key === ' ') {
                                                                e.preventDefault(); e.stopPropagation();
                                                                markRead(n.notification_id);
                                                            }
                                                        }}
                                                        className="opacity-0 group-hover:opacity-100 transition-opacity p-1 cursor-pointer text-slate-400 hover:text-brand-600"
                                                    >
                                                        <Check size={14} />
                                                    </span>
                                                )}
                                            </button>
                                        </li>
                                    );
                                })}
                            </ul>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}
