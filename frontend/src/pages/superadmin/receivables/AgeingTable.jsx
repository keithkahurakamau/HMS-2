import React from 'react';
import { Wallet, PauseCircle } from 'lucide-react';
import EmptyState from '../../../components/EmptyState';
import { formatKes, isZeroMoney } from '../../../api/receivables';

// One column per ageing bucket, in the order the backend returns the keys.
// `current` never carries warning colour: an outstanding-but-current balance
// is a normal invoice waiting for its due date, not a problem. Severity
// ramps only across the genuinely overdue buckets.
const BUCKETS = [
    { key: 'current', label: 'Current' },
    { key: 'b1_30', label: '1-30 days' },
    { key: 'b31_60', label: '31-60 days' },
    { key: 'b61_90', label: '61-90 days' },
    { key: 'b90_plus', label: '90+ days' },
];

function bucketToneClass(key, value) {
    if (key === 'current') return 'text-ink-700 dark:text-ink-300';
    if (isZeroMoney(value)) return 'text-ink-400 dark:text-ink-500';
    switch (key) {
        case 'b1_30':
            return 'text-amber-700 dark:text-amber-400';
        case 'b31_60':
            return 'text-amber-800 dark:text-amber-300 font-semibold';
        case 'b61_90':
            return 'text-rose-700 dark:text-rose-400 font-semibold';
        case 'b90_plus':
            return 'text-rose-800 dark:text-rose-300 font-bold';
        default:
            return 'text-ink-700 dark:text-ink-300';
    }
}

/**
 * AgeingTable: one row per hospital, bucketed by how overdue its balance is.
 *
 * A row is a button in disguise: click (or Enter/Space when focused) opens
 * the tenant drawer via `onSelect(tenantId)`. A tenant with reminders paused
 * gets a chip next to its name so a quiet account never reads as a healthy
 * one at a glance.
 */
export default function AgeingTable({ rows, onSelect }) {
    if (!rows || rows.length === 0) {
        return (
            <EmptyState
                icon={Wallet}
                title="No outstanding balances"
                body="Every tenant is paid up. Nothing is owed on the receivables ledger right now."
                tone="accent"
            />
        );
    }

    const handleKeyDown = (event, tenantId) => {
        if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            onSelect(tenantId);
        }
    };

    return (
        <div className="overflow-auto max-h-[70vh]">
            <table className="table-clean table-sticky">
                <thead>
                    <tr>
                        <th>Tenant</th>
                        {BUCKETS.map((bucket) => (
                            <th key={bucket.key} className="num">{bucket.label}</th>
                        ))}
                        <th className="num">Total</th>
                    </tr>
                </thead>
                <tbody>
                    {rows.map((row) => (
                        <tr
                            key={row.tenant_id}
                            role="button"
                            tabIndex={0}
                            onClick={() => onSelect(row.tenant_id)}
                            onKeyDown={(event) => handleKeyDown(event, row.tenant_id)}
                            className="cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand-500"
                        >
                            <td>
                                <div className="flex items-center gap-2 min-w-0">
                                    <span className="font-semibold text-ink-900 dark:text-white truncate">
                                        {row.tenant_name}
                                    </span>
                                    {row.reminders_paused && (
                                        <span className="badge-warn inline-flex items-center gap-1 shrink-0">
                                            <PauseCircle size={10} aria-hidden="true" />
                                            Reminders paused
                                        </span>
                                    )}
                                </div>
                            </td>
                            {BUCKETS.map((bucket) => (
                                <td key={bucket.key} className={`num tnum ${bucketToneClass(bucket.key, row[bucket.key])}`}>
                                    {formatKes(row[bucket.key])}
                                </td>
                            ))}
                            <td className="num tnum font-semibold text-ink-900 dark:text-white">
                                {formatKes(row.total)}
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}
