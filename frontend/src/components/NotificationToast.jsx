import React from 'react';
import { X } from 'lucide-react';
import { NOTIFICATION_CATEGORY_ICONS, NOTIFICATION_CATEGORY_STYLE } from '../constants/notificationCategories';

/* ──────────────────────────────────────────────────────────────────────────
 * NotificationToast — the live "sneak peek" popup for a just-arrived
 * notification (see useNotificationSocket). Rendered via react-hot-toast's
 * toast.custom(), which handles the auto-dismiss timer itself; this
 * component is just the card. Clicking it behaves like clicking the same
 * row in the bell dropdown (mark read + navigate); the notification is
 * already in the bell's list underneath by the time this is on screen, so
 * it stays there after the toast times out.
 * ────────────────────────────────────────────────────────────────────────── */
export default function NotificationToast({ notification, visible, onClick, onDismiss }) {
    const Icon = NOTIFICATION_CATEGORY_ICONS[notification.category] || NOTIFICATION_CATEGORY_ICONS.info;
    const style = NOTIFICATION_CATEGORY_STYLE[notification.category] || NOTIFICATION_CATEGORY_STYLE.info;

    return (
        <div
            role="status"
            className={`relative w-80 max-w-[calc(100vw-2rem)] bg-white dark:bg-ink-900 border border-ink-200/70 dark:border-ink-700 rounded-2xl shadow-elevated overflow-hidden ${visible ? 'animate-slide-in-right' : 'opacity-0'}`}
        >
            <button type="button" onClick={onClick} className="w-full text-left pl-4 pr-8 py-3 hover:bg-ink-50/60 dark:hover:bg-ink-800/50 transition-colors flex gap-3 cursor-pointer">
                <span className={`shrink-0 size-9 rounded-xl flex items-center justify-center ring-1 ring-inset ${style.ring}`} aria-hidden="true">
                    <Icon size={16} />
                </span>
                <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold text-ink-900 dark:text-white truncate">{notification.title}</p>
                    {notification.body && (
                        <p className="text-xs text-ink-500 dark:text-ink-400 mt-0.5 line-clamp-2 leading-relaxed">{notification.body}</p>
                    )}
                </div>
            </button>
            <button
                type="button"
                onClick={onDismiss}
                aria-label="Dismiss notification"
                className="absolute top-2 right-2 p-1 rounded-md text-ink-400 hover:text-ink-700 dark:hover:text-ink-200 hover:bg-ink-100 dark:hover:bg-ink-800"
            >
                <X size={14} />
            </button>
        </div>
    );
}
