import React, { useCallback, useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { Wallet, Banknote, HandCoins, AlertTriangle, PlayCircle } from 'lucide-react';
import PageHeader from '../../components/PageHeader';
import StatTile from '../../components/StatTile';
import Toolbar from '../../components/ui/Toolbar';
import { SkeletonTable } from '../../components/ui/Skeleton';
import ErrorState from '../../components/ui/ErrorState';
import { getSummary, getAgeing, runBillingNow, formatKes, isZeroMoney } from '../../api/receivables';
import AgeingTable from './receivables/AgeingTable';
import TenantDrawer from './receivables/TenantDrawer';

/**
 * Receivables: the operator's view of what every hospital owes the platform.
 *
 * Four totals up top (billed, received, outstanding, overdue), then one row
 * per tenant bucketed by how overdue its balance is. Clicking a row opens
 * the drawer for that tenant's invoices and payments. "Run billing now"
 * shares the same lock as the daily cron: a SKIPPED result means the cron
 * already ran, which is a normal outcome, not a failure.
 */
export default function Receivables() {
    const [summary, setSummary] = useState(null);
    const [rows, setRows] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [running, setRunning] = useState(false);
    const [selectedTenantId, setSelectedTenantId] = useState(null);

    const load = useCallback(async ({ silent = false } = {}) => {
        if (!silent) setLoading(true);
        if (!silent) setError(null);
        try {
            const [summaryData, ageingRows] = await Promise.all([getSummary(), getAgeing()]);
            setSummary(summaryData);
            setRows(ageingRows);
        } catch (err) {
            const message = err?.response?.data?.detail || 'Could not load the receivables ledger.';
            if (silent) toast.error(message); else setError(message);
        } finally {
            if (!silent) setLoading(false);
        }
    }, []);

    useEffect(() => { load(); }, [load]);

    const handleRunBilling = async () => {
        setRunning(true);
        try {
            const result = await runBillingNow();
            if (result.skipped) {
                // Another run (the daily cron) already holds the lock. Normal,
                // not an error: never toast.error() this.
                toast(result.message);
            } else if (!result.ok) {
                toast.error(result.message);
            } else {
                toast.success(result.message);
            }
            await load({ silent: true });
        } catch (err) {
            toast.error(err?.response?.data?.detail || 'Could not run billing.');
        } finally {
            setRunning(false);
        }
    };

    const overdueTone = summary && !isZeroMoney(summary.overdue) ? 'rose' : 'brand';

    return (
        <div className="space-y-6 animate-fade-in">
            <PageHeader
                eyebrow="Console"
                icon={Wallet}
                title="Receivables"
                subtitle="What every hospital owes the platform: billed, received, outstanding and overdue, all in one ledger."
                tone="accent"
            />

            <Toolbar
                left={<span className="text-xs text-ink-500 dark:text-ink-400">Runs on the same lock as the daily billing cron.</span>}
                right={(
                    <button
                        type="button"
                        onClick={handleRunBilling}
                        disabled={running}
                        className="btn btn-primary btn-xs"
                    >
                        <PlayCircle size={14} aria-hidden="true" />
                        {running ? 'Running…' : 'Run billing now'}
                    </button>
                )}
            />

            {loading && <SkeletonTable rows={8} cols={6} label="Loading receivables" />}
            {!loading && error && <ErrorState title="Could not load receivables" message={error} onRetry={load} />}

            {!loading && !error && summary && rows && (
                <>
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                        <StatTile icon={Banknote} label="Billed" value={formatKes(summary.billed)} tone="brand" hint="Total invoiced to date" />
                        <StatTile icon={HandCoins} label="Received" value={formatKes(summary.received)} tone="teal" hint="Total collected to date" />
                        <StatTile icon={Wallet} label="Outstanding" value={formatKes(summary.outstanding)} tone="accent" hint="Still owed, any age" />
                        <StatTile icon={AlertTriangle} label="Overdue" value={formatKes(summary.overdue)} tone={overdueTone} hint="Past its due date" />
                    </div>

                    <div className="card overflow-hidden">
                        <div className="p-4 border-b border-ink-200 dark:border-ink-800">
                            <h2 className="text-sm font-semibold text-ink-900 dark:text-white tracking-tight">Ageing by tenant</h2>
                            <p className="text-xs text-ink-500 dark:text-ink-400 mt-0.5">Click a hospital to see its invoices and payments.</p>
                        </div>
                        <AgeingTable rows={rows} onSelect={setSelectedTenantId} />
                    </div>
                </>
            )}

            {selectedTenantId != null && (
                <TenantDrawer
                    tenantId={selectedTenantId}
                    onClose={() => setSelectedTenantId(null)}
                    onChanged={() => load({ silent: true })}
                />
            )}
        </div>
    );
}
