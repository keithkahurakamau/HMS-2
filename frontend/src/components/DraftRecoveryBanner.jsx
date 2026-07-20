import React from 'react';
import { History, Check, X } from 'lucide-react';

// How long ago `date` was, in the coarse "3 minutes ago" style — no new
// dependency, just enough precision for a recovery prompt.
function timeAgo(date) {
    const seconds = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
    if (seconds < 60) return 'moments ago';
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes} minute${minutes === 1 ? '' : 's'} ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours} hour${hours === 1 ? '' : 's'} ago`;
    const days = Math.floor(hours / 24);
    return `${days} day${days === 1 ? '' : 's'} ago`;
}

/* ──────────────────────────────────────────────────────────────────────────
 * DraftRecoveryBanner — paired with useDraftSafetyNet. Shown wherever a
 * hasSavedDraft is true; lets the clinician see there's unsaved work waiting
 * and explicitly choose to bring it back (verbatim) or drop it. Never
 * decides for them.
 * ────────────────────────────────────────────────────────────────────────── */
export default function DraftRecoveryBanner({ savedAt, onRestore, onDiscard, label = 'notes' }) {
    return (
        <div className="flex items-center justify-between gap-3 rounded-xl border border-amber-200 dark:border-amber-500/20 bg-amber-50 dark:bg-amber-500/10 px-4 py-3">
            <div className="flex items-center gap-2.5 min-w-0">
                <History size={16} className="text-amber-600 dark:text-amber-400 shrink-0" />
                <p className="text-sm text-amber-800 dark:text-amber-200">
                    <span className="font-semibold">Unsaved {label} found</span>
                    {savedAt && <span className="text-amber-700 dark:text-amber-300"> from {timeAgo(savedAt)}</span>}
                    — restore them?
                </p>
            </div>
            <div className="flex items-center gap-2 shrink-0">
                <button
                    type="button"
                    onClick={onRestore}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-amber-600 text-white hover:bg-amber-700 transition-colors"
                >
                    <Check size={13} /> Restore
                </button>
                <button
                    type="button"
                    onClick={onDiscard}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-amber-700 dark:text-amber-300 hover:bg-amber-100 dark:hover:bg-amber-500/15 transition-colors"
                >
                    <X size={13} /> Discard
                </button>
            </div>
        </div>
    );
}
