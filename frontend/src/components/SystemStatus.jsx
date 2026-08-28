import React, { useCallback, useEffect, useRef, useState } from 'react';
import { WifiHigh, WifiLow, WifiOff } from 'lucide-react';

/**
 * SystemStatus: the live connection indicator in the workspace top bar.
 *
 *  This replaces a hardcoded "System Online" pill that reported nothing. It now
 *  answers the only question the label implies: can this browser reach the
 *  MediFleet API right now, and how quickly?
 *
 *  Two independent signals, because they fail differently and the fix differs:
 *
 *    - navigator.onLine says whether the device has a network at all. When it
 *      is false there is nothing to probe, so we do not waste a request.
 *    - A GET to /api/health says whether the API itself is answering. The
 *      browser can be happily on wifi while the server is down, which is the
 *      case the old pill hid.
 *
 *  Round-trip time separates "reachable" from "usable": on a ward tablet over
 *  weak hospital wifi the request completes but takes seconds, and staff need
 *  to know that before they blame themselves for a slow save.
 *
 *  State is always carried in the text, never by colour alone.
 */

const PROBE_URL = '/api/health';
const POLL_MS = 30000;      // quiet background cadence
const SLOW_MS = 1200;       // above this, call the link slow rather than healthy
const TIMEOUT_MS = 8000;    // a probe that hangs this long counts as unreachable

const STATES = {
    online: {
        Icon: WifiHigh,
        label: 'Online',
        tone: 'bg-accent-50 dark:bg-accent-700/15 ring-accent-100 dark:ring-accent-700/30 text-accent-700 dark:text-accent-400',
        dot: 'bg-accent-600',
    },
    slow: {
        Icon: WifiLow,
        label: 'Slow link',
        tone: 'bg-amber-50 dark:bg-amber-500/10 ring-amber-100 dark:ring-amber-500/25 text-amber-700 dark:text-amber-400',
        dot: 'bg-amber-500',
    },
    unreachable: {
        Icon: WifiOff,
        label: 'No server',
        tone: 'bg-rose-50 dark:bg-rose-500/10 ring-rose-100 dark:ring-rose-500/25 text-rose-700 dark:text-rose-400',
        dot: 'bg-rose-500',
    },
    offline: {
        Icon: WifiOff,
        label: 'Offline',
        tone: 'bg-ink-100 dark:bg-ink-800 ring-ink-200 dark:ring-ink-700 text-ink-600 dark:text-ink-300',
        dot: 'bg-ink-400',
    },
    checking: {
        Icon: WifiLow,
        label: 'Checking',
        tone: 'bg-ink-100 dark:bg-ink-800 ring-ink-200 dark:ring-ink-700 text-ink-500 dark:text-ink-400',
        dot: 'bg-ink-400',
    },
};

export default function SystemStatus() {
    const [state, setState] = useState('checking');
    const [rtt, setRtt] = useState(null);
    const [checkedAt, setCheckedAt] = useState(null);
    const timer = useRef(null);

    const probe = useCallback(async () => {
        if (!navigator.onLine) {
            setState('offline');
            setRtt(null);
            return;
        }
        const started = performance.now();
        const controller = new AbortController();
        const abort = setTimeout(() => controller.abort(), TIMEOUT_MS);
        try {
            const res = await fetch(PROBE_URL, { cache: 'no-store', signal: controller.signal });
            const elapsed = Math.round(performance.now() - started);
            setRtt(elapsed);
            setCheckedAt(new Date());
            if (!res.ok) setState('unreachable');
            else setState(elapsed > SLOW_MS ? 'slow' : 'online');
        } catch {
            setRtt(null);
            setCheckedAt(new Date());
            setState('unreachable');
        } finally {
            clearTimeout(abort);
        }
    }, []);

    useEffect(() => {
        probe();
        timer.current = setInterval(() => {
            // Skip the poll while the tab is hidden: nobody is reading the pill,
            // and a ward machine can sit on a background tab for hours.
            if (document.visibilityState === 'visible') probe();
        }, POLL_MS);

        const onOnline = () => probe();
        const onOffline = () => { setState('offline'); setRtt(null); };
        const onVisible = () => { if (document.visibilityState === 'visible') probe(); };

        window.addEventListener('online', onOnline);
        window.addEventListener('offline', onOffline);
        document.addEventListener('visibilitychange', onVisible);
        return () => {
            clearInterval(timer.current);
            window.removeEventListener('online', onOnline);
            window.removeEventListener('offline', onOffline);
            document.removeEventListener('visibilitychange', onVisible);
        };
    }, [probe]);

    const s = STATES[state];
    const { Icon } = s;

    const detail = [
        state === 'offline' ? 'This device has no network connection.'
            : state === 'unreachable' ? 'The MediFleet API is not responding.'
                : state === 'slow' ? 'The API is answering, but slowly.'
                    : state === 'online' ? 'The MediFleet API is responding normally.'
                        : 'Checking the connection.',
        // Only quote timing when the API actually answered: a fast error
        // response would otherwise read as 'not responding, 11 ms'.
        rtt != null && (state === 'online' || state === 'slow') ? `Round trip ${rtt} ms.` : null,
        checkedAt ? `Checked ${checkedAt.toLocaleTimeString()}.` : null,
    ].filter(Boolean).join(' ');

    return (
        <div
            role="status"
            aria-live="polite"
            title={detail}
            className={`hidden sm:flex items-center gap-2 pl-2.5 pr-3 py-1.5 rounded-full ring-1 ring-inset ${s.tone}`}
        >
            <Icon size={13} aria-hidden="true" />
            <span className="text-2xs font-semibold uppercase tracking-wider">{s.label}</span>
            {rtt != null && (state === 'online' || state === 'slow') && (
                <span className="tnum text-2xs opacity-70">{rtt}ms</span>
            )}
        </div>
    );
}
