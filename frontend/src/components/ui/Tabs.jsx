import React, { useRef } from 'react';

/**
 * Tabs: the one tab treatment for the whole workspace.
 *
 *  Every module page used to hand-roll its own tab row, which is why no two of
 *  them agreed on height, spacing or the active state. This replaces them.
 *
 *  Keyboard behaviour follows the WAI-ARIA tabs pattern: only the active tab is
 *  in the page tab order, and left/right move between tabs with wraparound, so
 *  a keyboard user does not have to tab through eleven of them to reach the
 *  panel.
 *
 *  The active indicator animates scaleX from 0 to 1 rather than sliding a
 *  positioned bar, and the transition is CSS rather than a keyframe, so an
 *  interrupted change reverses from wherever it currently is instead of
 *  snapping. The button itself is never scaled, only the underline.
 *
 *  Props:
 *   - items:    [{ id, label, count? }]. `count` renders a neutral badge.
 *   - activeId: the currently selected item id.
 *   - onChange: (id) => void, called on click and on arrow key.
 */
export default function Tabs({ items, activeId, onChange }) {
    const refs = useRef([]);

    const handleKeyDown = (event, index) => {
        const delta = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0;
        if (!delta) return;
        event.preventDefault();
        const next = (index + delta + items.length) % items.length;
        refs.current[next]?.focus();
        onChange(items[next].id);
    };

    return (
        <div role="tablist" className="flex items-center gap-1 border-b border-ink-200 dark:border-ink-800">
            {items.map((item, index) => {
                const active = item.id === activeId;
                return (
                    <button
                        key={item.id}
                        ref={(node) => { refs.current[index] = node; }}
                        type="button"
                        role="tab"
                        aria-selected={active}
                        tabIndex={active ? 0 : -1}
                        onClick={() => onChange(item.id)}
                        onKeyDown={(event) => handleKeyDown(event, index)}
                        className={[
                            'relative inline-flex items-center gap-2 px-3 text-sm font-medium',
                            'focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 rounded-t-md',
                            active
                                ? 'text-brand-700 dark:text-brand-300'
                                : 'text-ink-500 dark:text-ink-400 hover:text-ink-700 dark:hover:text-ink-200',
                        ].join(' ')}
                        style={{ height: 'var(--ctl-h)', transition: 'color var(--dur-fast) var(--ease-out)' }}
                    >
                        {item.label}
                        {typeof item.count === 'number' && (
                            <span className="badge-neutral tnum">{item.count}</span>
                        )}
                        <span
                            aria-hidden="true"
                            className="absolute inset-x-0 -bottom-px h-0.5 origin-left bg-brand-600"
                            style={{
                                transform: `scaleX(${active ? 1 : 0})`,
                                transition: 'transform var(--dur) var(--ease-out)',
                            }}
                        />
                    </button>
                );
            })}
        </div>
    );
}
