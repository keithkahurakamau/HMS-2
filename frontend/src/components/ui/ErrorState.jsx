import React from 'react';
import { AlertTriangle } from 'lucide-react';

/**
 * ErrorState — the "this did not load" state for any collection surface.
 *
 *  The fourth of the four states every list, table, board and panel ships:
 *  empty (EmptyState), loading (SkeletonTable), error (this), and denied
 *  (ModuleGuard's UpgradeRequired).
 *
 *  Announced as an alert, because unlike an empty state this is unexpected and
 *  the user needs to know without hunting for it.
 *
 *  Props:
 *   - title:   what failed, in plain words ("Could not load patients").
 *   - message: optional detail, one or two sentences.
 *   - onRetry: optional handler. The retry button only renders when given one,
 *              because a button that cannot help is worse than no button.
 */
export default function ErrorState({ title, message, onRetry }) {
    return (
        <div role="alert" className="empty">
            <AlertTriangle className="h-8 w-8 text-status-critical" aria-hidden="true" />
            <p className="t-title">{title}</p>
            {message && <p className="t-body max-w-sm">{message}</p>}
            {onRetry && (
                <button type="button" className="btn btn-secondary" onClick={onRetry}>
                    Try again
                </button>
            )}
        </div>
    );
}
