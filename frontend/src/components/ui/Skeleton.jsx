import React from 'react';

/**
 * Skeleton: a single loading placeholder block.
 *
 *  Size it with utilities: <Skeleton className="h-5 w-32" />.
 *
 *  Hidden from assistive technology on purpose. A screen reader user gains
 *  nothing from hearing "grey rectangle" eleven times; SkeletonTable below
 *  announces the loading state once instead.
 */
export function Skeleton({ className = '' }) {
    return <div data-testid="skeleton" aria-hidden="true" className={`skeleton ${className}`.trim()} />;
}

/**
 * SkeletonTable: a placeholder grid shaped like the table that is loading.
 *
 *  Prefer this over a spinner for tabular data. It holds the layout still, so
 *  rows do not jump when the real data lands, and it tells the eye where to
 *  wait. One polite live region carries the announcement for the whole grid.
 *
 *  Props:
 *   - rows: number of placeholder rows (default 5).
 *   - cols: number of placeholder columns (default 4).
 *   - label: what is loading, for screen readers (default "Loading").
 */
export function SkeletonTable({ rows = 5, cols = 4, label = 'Loading' }) {
    return (
        <div role="status" aria-live="polite" className="w-full">
            <span className="sr-only">{label}</span>
            <div className="flex flex-col gap-2">
                {Array.from({ length: rows }).map((_, rowIndex) => (
                    <div key={rowIndex} className="flex gap-2">
                        {Array.from({ length: cols }).map((_, colIndex) => (
                            <Skeleton key={colIndex} className="h-5 flex-1" />
                        ))}
                    </div>
                ))}
            </div>
        </div>
    );
}

export default Skeleton;
