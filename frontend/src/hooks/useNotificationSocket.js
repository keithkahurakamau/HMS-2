import { useEffect, useRef } from 'react';

/* ──────────────────────────────────────────────────────────────────────────
 * useNotificationSocket — live push for the notification bell.
 *
 * While `enabled` is true and a userId is known, opens an authenticated
 * WebSocket to /ws/notifications/{userId}. `notify()` (backend/app/utils/
 * notify.py) publishes a `notification` frame the instant a row is created,
 * so the bell updates and a sneak-peek toast can appear without waiting for
 * NotificationBell's 30s poll, which stays in place as the fallback (no
 * Redis multi-worker, dropped socket, tab was closed when it fired, etc.).
 *
 * Mirrors usePaymentSocket.js's connect/cleanup shape.
 *
 *   enabled  boolean — open the socket only while the bell is mounted/live
 *   userId   the signed-in user's id (matches the JWT the cookie carries —
 *            the server closes the socket if these don't match)
 *   role     optional — opts into role-channel broadcasts (e.g. every Lab
 *            Technician notified of a new STAT order)
 *   onEvent  (data) => void — called per `type: "notification"` frame
 * ────────────────────────────────────────────────────────────────────────── */
export default function useNotificationSocket(enabled, userId, role, onEvent) {
    // Keep the latest callback in a ref so the socket effect doesn't need to
    // reconnect every render. Updated in an effect (not during render) per the
    // rules of hooks.
    const cbRef = useRef(onEvent);
    useEffect(() => { cbRef.current = onEvent; });

    useEffect(() => {
        // A single cleanup function owns whatever this effect allocates —
        // `socket` stays null on any bailout path (disabled, no userId,
        // constructor throws) so cleanup is unconditional and guaranteed
        // rather than living behind an early `return undefined`.
        let socket = null;

        if (enabled && userId) {
            const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const query = role ? `?role=${encodeURIComponent(role)}` : '';
            const url = `${proto}//${window.location.host}/ws/notifications/${encodeURIComponent(userId)}${query}`;

            try {
                socket = new WebSocket(url);
                socket.onmessage = (evt) => {
                    let data;
                    try { data = JSON.parse(evt.data); } catch { return; }
                    if (data && data.type === 'notification') cbRef.current?.(data);
                };
                // Swallow errors — polling is the safety net.
                socket.onerror = () => {};
            } catch {
                socket = null; // fall back to polling
            }
        }

        return () => {
            if (!socket) return;
            try {
                if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) {
                    socket.close();
                }
            } catch { /* noop */ }
        };
    }, [enabled, userId, role]);
}
