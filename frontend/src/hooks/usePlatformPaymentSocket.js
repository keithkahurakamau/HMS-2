import { useEffect, useRef } from 'react';

/* ──────────────────────────────────────────────────────────────────────────
 * usePlatformPaymentSocket — live subscription-billing updates for the
 * superadmin console.
 *
 * While `enabled` is true, opens a WebSocket to the platform feed
 * (/ws/payments/platform), authenticated by the superadmin_token cookie. The
 * platform webhook publishes a `platform_payment_update` frame the instant a
 * subscription charge settles, so the operator watches it flip to
 * success/failure without polling. Polling stays as a fallback.
 *
 *   enabled  boolean — open the socket only while watching for charges
 *   onEvent  (data) => void — called per platform_payment_update frame
 * ────────────────────────────────────────────────────────────────────────── */
export default function usePlatformPaymentSocket(enabled, onEvent) {
    const cbRef = useRef(onEvent);
    useEffect(() => { cbRef.current = onEvent; });

    useEffect(() => {
        if (!enabled) return undefined;

        const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const url = `${proto}//${window.location.host}/ws/payments/platform`;

        let socket;
        try {
            socket = new WebSocket(url);
        } catch {
            return undefined; // fall back to polling
        }

        socket.onmessage = (evt) => {
            let data;
            try { data = JSON.parse(evt.data); } catch { return; }
            if (data && data.type === 'platform_payment_update') cbRef.current?.(data);
        };
        socket.onerror = () => {};

        return () => {
            try {
                if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) {
                    socket.close();
                }
            } catch { /* noop */ }
        };
    }, [enabled]);
}
