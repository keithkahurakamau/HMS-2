import React from 'react';

/**
 * EmptyState — the "nothing here yet" card.
 *
 *  Replaces the half-dozen variations of "centered icon + headline + helper
 *  text + maybe a button" sprinkled through the pages. Stays in the same
 *  visual register as the rest of the workspace.
 *
 *  Props:
 *   - icon:      Lucide icon component.
 *   - title:     Bold one-liner.
 *   - body:      One-or-two-sentence helper text (optional).
 *   - action:    Optional <button>/<Link> rendered below body.
 *   - tone:      brand | teal | accent | warning | rose | neutral.
 *   - surface:   light (default) | dark — flip to dark on the superadmin console.
 *   - dense:     If true, removes top/bottom padding so the empty state slots
 *                into smaller containers (e.g. inside a list column).
 */
export default function EmptyState({
    icon: Icon,
    title,
    body,
    action,
    tone = 'brand',
    surface = 'light',
    dense = false,
}) {
    const isDark = surface === 'dark';

    const chip = (() => {
        if (isDark) {
            return {
                brand:   'bg-brand-500/10 text-brand-300 ring-brand-500/20',
                teal:    'bg-teal-500/10 text-teal-300 ring-teal-500/20',
                accent:  'bg-accent-500/10 text-accent-300 ring-accent-500/20',
                warning: 'bg-amber-500/10 text-amber-300 ring-amber-500/20',
                rose:    'bg-rose-500/10 text-rose-300 ring-rose-500/20',
                neutral: 'bg-white/[0.06] text-ink-200 ring-white/10',
            }[tone];
        }
        return {
            brand:   'bg-brand-50 text-brand-700 ring-brand-100',
            teal:    'bg-teal-50 text-teal-700 ring-teal-100',
            accent:  'bg-accent-50 text-accent-700 ring-accent-100',
            warning: 'bg-amber-50 text-amber-700 ring-amber-100',
            rose:    'bg-rose-50 text-rose-700 ring-rose-100',
            neutral: 'bg-ink-100 text-ink-700 ring-ink-200',
        }[tone];
    })();

    return (
        <div
            className={[
                'rounded-2xl border border-dashed text-center',
                isDark ? 'border-white/10 bg-white/[0.02]' : 'border-ink-300 bg-white/60',
                dense ? 'p-6' : 'p-10 sm:p-14',
            ].join(' ')}
        >
            {Icon && (
                <div className={`mx-auto w-14 h-14 rounded-2xl flex items-center justify-center ring-1 ring-inset ${chip}`}>
                    <Icon size={22} aria-hidden="true" />
                </div>
            )}
            <h3 className={`mt-4 text-base font-semibold tracking-tight ${isDark ? 'text-white' : 'text-ink-900'}`}>
                {title}
            </h3>
            {body && (
                <p className={`mt-1.5 text-sm max-w-md mx-auto leading-relaxed ${isDark ? 'text-ink-400' : 'text-ink-500'}`}>
                    {body}
                </p>
            )}
            {action && <div className="mt-5 inline-flex">{action}</div>}
        </div>
    );
}
