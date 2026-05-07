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

// Map each category to a tinted icon container — the rail/icon colour is the
// only place categories should differ. Cards themselves stay neutral so the
// overall inbox doesn't feel like a Christmas tree.
const CATEGORY_STYLE = {
    info:     { ring: 'bg-blue-50 ring-blue-100 text-blue-600',
                rail: 'bg-blue-500',     label: 'text-blue-700' },
    success:  { ring: 'bg-accent-50 ring-accent-100 text-accent-600',
                rail: 'bg-accent-500',   label: 'text-accent-700' },
    warning:  { ring: 'bg-amber-50 ring-amber-100 text-amber-600',
                rail: 'bg-amber-500',    label: 'text-amber-700' },
    critical: { ring: 'bg-rose-50 ring-rose-100 text-rose-600',
                rail: 'bg-rose-500',     label: 'text-rose-700' },
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

    useEffect(() => {
        fetchNotifications();
        const id = setInterval(fetchNotifications, POLL_INTERVAL_MS);
        return () => clearInterval(id);
    }, [fetchNotifications]);

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
                className="relative p-2 text-ink-500 hover:text-ink-900 dark:text-ink-300 dark:hover:text-white rounded-lg hover:bg-ink-100 dark:hover:bg-ink-800 transition-colors"
            >
                <Bell size={20} aria-hidden="true" />
                {unreadCount > 0 && (
                    <span
                        className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] px-1 bg-rose-500 text-white text-[10px] font-bold rounded-full flex items-center justify-center ring-2 ring-white dark:ring-ink-900"
                        aria-hidden="true"
                    >
                        {unreadCount > 99 ? '99+' : unreadCount}
                    </span>
                )}
            </button>

            {/* Backdrop — closes the panel when clicking the page content */}
            {open && (
                <div
                    className="fixed inset-0 z-[60] bg-transparent"
                    onClick={() => setOpen(false)}
                    aria-hidden="true"
                />
            )}

            {open && (
                <div
                    role="dialog"
                    aria-label="Notification inbox"
                    className="absolute right-0 mt-2 w-96 max-w-[calc(100vw-2rem)]
                               bg-white dark:bg-ink-900
                               border border-ink-200/70 dark:border-ink-700
                               rounded-2xl shadow-elevated overflow-hidden
                               z-[70] animate-slide-in-right"
                >
                    <div className="px-4 py-3 border-b border-ink-100 dark:border-ink-800 flex items-center justify-between bg-ink-50/60 dark:bg-ink-950/40">
                        <div>
                            <h3 className="font-semibold text-ink-900 dark:text-white text-sm tracking-tight">Notifications</h3>
                            <p className="text-xs text-ink-500 mt-0.5">{unreadCount > 0 ? `${unreadCount} unread` : 'All caught up'}</p>
                        </div>
                        {unreadCount > 0 && (
                            <button
                                onClick={markAllRead}
                                className="text-xs font-semibold text-brand-600 hover:text-brand-700 flex items-center gap-1 px-2 py-1 rounded-md hover:bg-brand-50 transition-colors"
                            >
                                <CheckCheck size={14} /> Mark all read
                            </button>
                        )}
                    </div>

                    <div className="max-h-96 overflow-y-auto custom-scrollbar">
                        {notifications.length === 0 ? (
                            <div className="px-4 py-12 text-center text-ink-400 text-sm">
                                <Bell size={28} className="mx-auto mb-2 opacity-40" />
                                No notifications yet.
                            </div>
                        ) : (
                            <ul className="divide-y divide-ink-100 dark:divide-ink-800">
                                {notifications.map((n) => {
                                    const Icon = CATEGORY_ICONS[n.category] || Info;
                                    const style = CATEGORY_STYLE[n.category] || CATEGORY_STYLE.info;
                                    return (
                                        <li
                                            key={n.notification_id}
                                            className={`group relative ${!n.is_read ? 'bg-brand-50/30 dark:bg-brand-900/10' : ''}`}
                                        >
                                            {!n.is_read && (
                                                <span
                                                    className={`absolute left-0 top-3 bottom-3 w-1 rounded-r ${style.rail}`}
                                                    aria-hidden="true"
                                                />
                                            )}
                                            <button
                                                onClick={() => handleClick(n)}
                                                className="w-full text-left px-4 py-3 hover:bg-ink-50/60 dark:hover:bg-ink-800/50 transition-colors flex gap-3"
                                            >
                                                <span
                                                    className={`shrink-0 w-9 h-9 rounded-xl flex items-center justify-center ring-1 ring-inset ${style.ring}`}
                                                    aria-hidden="true"
                                                >
                                                    <Icon size={16} />
                                                </span>
                                                <div className="flex-1 min-w-0">
                                                    <div className="flex items-center gap-2">
                                                        <p className={`text-sm truncate ${n.is_read ? 'text-ink-700 dark:text-ink-300' : 'font-semibold text-ink-900 dark:text-white'}`}>
                                                            {n.title}
                                                        </p>
                                                    </div>
                                                    {n.body && (
                                                        <p className="text-xs text-ink-500 dark:text-ink-400 mt-0.5 line-clamp-2 leading-relaxed">
                                                            {n.body}
                                                        </p>
                                                    )}
                                                    <p className="text-2xs text-ink-400 dark:text-ink-500 mt-1.5 uppercase tracking-wider font-semibold">
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
                                                        className="opacity-0 group-hover:opacity-100 transition-opacity p-1 cursor-pointer text-ink-400 hover:text-brand-600 self-start mt-1"
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
