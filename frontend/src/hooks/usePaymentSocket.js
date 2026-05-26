import { useEffect, useRef } from 'react';

/* ──────────────────────────────────────────────────────────────────────────
 * usePaymentSocket — live M-Pesa payment updates for the checkout screens.
 *
 * While `enabled` is true, opens an authenticated WebSocket to the tenant's
 * payment feed (/ws/payments/{tenant_db}). The webhook publishes a
 * `payment_update` frame the instant a receipt settles, so the spinner flips
 * to success/failure without waiting for the next poll. Polling stays in place
 * as a fallback (no Redis multi-worker, dropped socket, etc.).
 *
 *   enabled  boolean — open the socket only while a push is in flight
 *   onEvent  (data) => void — called per payment_update frame
 *
 * The tenant db_name is the same value the API client sends as X-Tenant-ID
 * (localStorage 'hms_tenant_id'); the cookie-based auth + server-side tenant
 * check keep one hospital from ever seeing another's feed.
 * ────────────────────────────────────────────────────────────────────────── */
export default function usePaymentSocket(enabled, onEvent) {
    const cbRef = useRef(onEvent);
    cbRef.current = onEvent;

    useEffect(() => {
        if (!enabled) return undefined;
        const tenant = localStorage.getItem('hms_tenant_id');
        if (!tenant) return undefined;

        const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const url = `${proto}//${window.location.host}/ws/payments/${encodeURIComponent(tenant)}`;

        let socket;
        let closed = false;
        try {
            socket = new WebSocket(url);
        } catch {
            return undefined; // fall back to polling
        }

        socket.onmessage = (evt) => {
            let data;
            try { data = JSON.parse(evt.data); } catch { return; }
            if (data && data.type === 'payment_update') cbRef.current?.(data);
        };
        // Swallow errors — polling is the safety net.
        socket.onerror = () => {};

        return () => {
            closed = true;
            try {
                if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) {
                    socket.close();
                }
            } catch { /* noop */ }
            void closed;
        };
    }, [enabled]);
}
