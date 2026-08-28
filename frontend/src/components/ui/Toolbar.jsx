import React from 'react';

/**
 * Toolbar: the filter and action bar that sits between a PageHeader and the
 * content it controls.
 *
 *  Module pages each invented their own version of this row, which is why
 *  search boxes, filter selects and primary actions sat at different heights
 *  and different distances from the table below them. This locks the pattern.
 *
 *  Controls placed inside inherit the surface density, so the same markup is
 *  roomy on the portal and tight in a clinical worklist.
 *
 *  Props:
 *   - left:   filters, search, segmented controls. Wraps on narrow screens.
 *   - right:  actions, usually one .btn-primary and some .btn-secondary.
 *   - sticky: pin to the top of the scroll container. Use when the content
 *             below scrolls independently, such as a long worklist.
 */
export default function Toolbar({ left, right, sticky = false }) {
    return (
        <div
            className={[
                'flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between',
                'py-2 mb-3 border-b border-ink-200 dark:border-ink-800',
                sticky ? 'sticky top-0 z-10 bg-ink-50 dark:bg-ink-950' : '',
            ].join(' ')}
        >
            <div className="flex items-center gap-2 flex-wrap min-w-0">{left}</div>
            {right && <div className="flex items-center gap-2 flex-wrap shrink-0">{right}</div>}
        </div>
    );
}
