import React, { useCallback, useEffect, useRef, useState } from 'react';
import { AlertTriangle, CheckCircle2, ChevronDown, RefreshCw } from 'lucide-react';
import { apiClient } from '../api/client';

/**
 * PlatformHealth: the always-on "what is wrong right now" listener for the
 * superadmin console.
 *
 *  The operator should never have to open four pages to discover that callbacks
 *  are dead or that subscription billing was never configured. This polls the
 *  checks that can silently break the platform and puts the answer in the
 *  console header, where it is visible on every screen.
 *
 *  What it watches:
 *    - API reachability, the same /api/health probe the workspace pill uses.
 *    - Pay Hero webhook readiness. That endpoint already returns a `blockers`
 *      list of human-readable reasons, and in production any blocker means
 *      every callback returns 500, so money silently stops settling.
 *    - Subscription billing configuration, the operator's own revenue rail.
 *
 *  A failed check is itself reported as an issue. Silence is not health: if the
 *  console cannot ask, the operator needs to know that too.
 */

const POLL_MS = 60000;

export default function PlatformHealth() {
    const [issues, setIssues] = useState(null);   // null while the first pass runs
    const [open, setOpen] = useState(false);
    const [checkedAt, setCheckedAt] = useState(null);
    const [busy, setBusy] = useState(false);
    const timer = useRef(null);

    const check = useCallback(async () => {
        setBusy(true);
        const found = [];

        if (!navigator.onLine) {
            found.push({ id: 'network', severity: 'critical', title: 'This device is offline', detail: 'The console cannot reach anything until the network returns.' });
        } else {
            try {
                const res = await fetch('/api/health', { cache: 'no-store' });
                if (!res.ok) {
                    found.push({ id: 'api', severity: 'critical', title: 'The API is not responding', detail: `Health check returned ${res.status}.` });
                }
            } catch {
                found.push({ id: 'api', severity: 'critical', title: 'The API is not responding', detail: 'The health check could not be reached at all.' });
            }
        }

        try {
            const { data } = await apiClient.get('/public/superadmin/payhero/webhook-health');
            (data?.blockers || []).forEach((blocker, i) => {
                found.push({
                    id: `webhook-${i}`,
                    // In production a blocker kills every callback; in development it is advisory.
                    severity: data.environment === 'production' ? 'critical' : 'warning',
                    title: 'Pay Hero callbacks are not ready',
                    detail: blocker,
                });
            });
        } catch {
            found.push({ id: 'webhook-check', severity: 'warning', title: 'Could not read webhook readiness', detail: 'The webhook health check did not answer.' });
        }

        try {
            const { data } = await apiClient.get('/public/superadmin/platform-payhero/health');
            if (!data?.config?.configured) {
                found.push({
                    id: 'billing',
                    severity: 'warning',
                    title: 'Subscription billing is not configured',
                    detail: 'The operator revenue rail cannot charge tenants until this is set up.',
                });
            }
        } catch {
            found.push({ id: 'billing-check', severity: 'warning', title: 'Could not read subscription billing status', detail: 'The billing health check did not answer.' });
        }

        setIssues(found);
        setCheckedAt(new Date());
        setBusy(false);
    }, []);

    useEffect(() => {
        check();
        timer.current = setInterval(() => {
            if (document.visibilityState === 'visible') check();
        }, POLL_MS);
        return () => clearInterval(timer.current);
    }, [check]);

    const count = issues?.length ?? 0;
    const critical = (issues || []).some((i) => i.severity === 'critical');
    const clear = issues !== null && count === 0;

    const tone = clear
        ? 'bg-accent-500/10 ring-accent-500/25 text-accent-300'
        : critical
            ? 'bg-rose-500/10 ring-rose-500/30 text-rose-300'
            : 'bg-amber-500/10 ring-amber-500/25 text-amber-300';

    const label = issues === null
        ? 'Checking platform'
        : clear
            ? 'All clear'
            : `${count} ${count === 1 ? 'issue' : 'issues'}`;

    return (
        <div className="relative" role="status" aria-live="polite">
            <button
                type="button"
                onClick={() => setOpen((v) => !v)}
                aria-expanded={open}
                className={`inline-flex items-center gap-2 pl-2.5 pr-2 py-1.5 rounded-full ring-1 ring-inset cursor-pointer transition-colors ${tone}`}
            >
                {clear
                    ? <CheckCircle2 size={13} aria-hidden="true" />
                    : <AlertTriangle size={13} aria-hidden="true" />}
                <span className="text-2xs font-semibold uppercase tracking-wider">{label}</span>
                <ChevronDown size={13} aria-hidden="true" className={open ? 'rotate-180 transition-transform' : 'transition-transform'} />
            </button>

            {open && (
                <div className="absolute right-0 mt-2 w-80 max-h-[60vh] overflow-y-auto overlay-surface p-3 z-50 custom-scrollbar">
                    <div className="flex items-center justify-between gap-2 mb-2">
                        <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-ink-500 dark:text-ink-400">
                            Platform health
                        </p>
                        <button
                            type="button"
                            onClick={check}
                            disabled={busy}
                            className="btn btn-ghost btn-xs"
                        >
                            <RefreshCw size={12} className={busy ? 'animate-spin' : ''} aria-hidden="true" />
                            Recheck
                        </button>
                    </div>

                    {clear ? (
                        <p className="t-body text-sm">
                            Every check passed. The API is answering, Pay Hero callbacks are wired, and
                            subscription billing is configured.
                        </p>
                    ) : (
                        <ul className="flex flex-col gap-2">
                            {(issues || []).map((issue) => (
                                <li
                                    key={issue.id}
                                    className={`rounded-lg border-l-2 pl-2.5 py-1.5 ${
                                        issue.severity === 'critical'
                                            ? 'border-status-critical bg-rose-50 dark:bg-rose-500/10'
                                            : 'border-status-warn bg-amber-50 dark:bg-amber-500/10'
                                    }`}
                                >
                                    <p className="text-xs font-semibold text-ink-900 dark:text-ink-100">
                                        {issue.severity === 'critical' ? 'Critical: ' : 'Warning: '}{issue.title}
                                    </p>
                                    <p className="text-xs text-ink-600 dark:text-ink-300">{issue.detail}</p>
                                </li>
                            ))}
                        </ul>
                    )}

                    {checkedAt && (
                        <p className="mt-2 pt-2 border-t border-ink-100 dark:border-ink-800 text-2xs text-ink-500 dark:text-ink-400">
                            Last checked {checkedAt.toLocaleTimeString()}, rechecks every minute.
                        </p>
                    )}
                </div>
            )}
        </div>
    );
}
