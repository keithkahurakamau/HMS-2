import React from 'react';

// Static tone lookups — declared at module scope so they're allocated once
// instead of rebuilt on every render (a fresh object each render defeats any
// memoization downstream). They reference no props/state.
// Light tones carry `dark:` companions so tiles on a workspace page (which
// render with the default light surface) flip cleanly when the app is in dark
// mode. The explicit DARK_TONE map below is only for the always-dark superadmin
// console (surface="dark"), which doesn't rely on the html.dark class.
const LIGHT_TONE = {
    brand:   'bg-brand-50 text-brand-700 ring-brand-100 dark:bg-brand-500/10 dark:text-brand-300 dark:ring-brand-500/20',
    teal:    'bg-teal-50 text-teal-700 ring-teal-100 dark:bg-teal-500/10 dark:text-teal-300 dark:ring-teal-500/20',
    accent:  'bg-accent-50 text-accent-700 ring-accent-100 dark:bg-accent-500/10 dark:text-accent-300 dark:ring-accent-500/20',
    warning: 'bg-amber-50 text-amber-700 ring-amber-100 dark:bg-amber-500/10 dark:text-amber-300 dark:ring-amber-500/20',
    rose:    'bg-rose-50 text-rose-700 ring-rose-100 dark:bg-rose-500/10 dark:text-rose-300 dark:ring-rose-500/20',
    neutral: 'bg-ink-100 text-ink-700 ring-ink-200 dark:bg-white/[0.06] dark:text-ink-200 dark:ring-white/10',
};
const DARK_TONE = {
    brand:   'bg-brand-500/10 text-brand-300 ring-brand-500/20',
    teal:    'bg-teal-500/10 text-teal-300 ring-teal-500/20',
    accent:  'bg-accent-500/10 text-accent-300 ring-accent-500/20',
    warning: 'bg-amber-500/10 text-amber-300 ring-amber-500/20',
    rose:    'bg-rose-500/10 text-rose-300 ring-rose-500/20',
    neutral: 'bg-white/[0.06] text-ink-200 ring-white/10',
};
const DELTA_COLORS = {
    accent: 'text-accent-600',
    rose:   'text-rose-600',
    ink:    'text-ink-500',
};

/**
 * StatTile — the canonical KPI / metric card.
 *
 *  Used everywhere a page shows a small fixed-precision number with context.
 *  Picks colors from the unified tone scale so a dashboard reads as one
 *  cohesive piece rather than a mosaic of ad-hoc tiles.
 *
 *  Props:
 *   - icon:       Lucide icon component.
 *   - label:      Uppercase eyebrow above the value.
 *   - value:      The primary number (string-formatted by the caller).
 *   - delta:      Optional `+12%` / `-3` accent under the value.
 *   - hint:       Optional one-liner below the value (preferred over delta
 *                 for context that isn't a comparison).
 *   - tone:       brand | teal | accent | warning | rose | neutral.
 *   - surface:    light (default) | dark — pick dark on the superadmin console.
 *   - onClick:    If provided, the tile becomes a button. Default is static.
 */
export default function StatTile({
    icon: Icon,
    label,
    value,
    delta,
    deltaTone = 'accent',
    hint,
    tone = 'brand',
    surface = 'light',
    onClick,
    children,
}) {
    const isDark = surface === 'dark';
    const tones = isDark ? DARK_TONE : LIGHT_TONE;
    const iconChip = tones[tone] || tones.brand;
    const deltaColor = DELTA_COLORS[deltaTone] || 'text-accent-600';

    const Wrapper = onClick ? 'button' : 'div';
    const wrapperProps = onClick ? { onClick, type: 'button' } : {};

    return (
        <Wrapper
            {...wrapperProps}
            className={[
                'group flex flex-col gap-4 p-5 sm:p-6 rounded-2xl transition-all duration-200 ring-1 ring-inset',
                isDark
                    ? 'bg-white/[0.04] backdrop-blur-md ring-white/10 hover:bg-white/[0.06] text-white'
                    : 'bg-white ring-ink-200/70 shadow-soft hover:shadow-elevated text-ink-900 dark:bg-white/[0.04] dark:ring-white/10 dark:hover:bg-white/[0.06] dark:text-white',
                onClick ? 'text-left cursor-pointer hover:-translate-y-0.5 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-brand-500/25' : '',
            ].join(' ')}
        >
            <div className="flex items-start justify-between gap-3">
                {Icon && (
                    <div className={`size-11 rounded-xl flex items-center justify-center ring-1 ring-inset ${iconChip}`}>
                        <Icon size={18} aria-hidden="true" />
                    </div>
                )}
                {delta != null && (
                    <span className={`text-xs font-semibold ${deltaColor}`}>{delta}</span>
                )}
            </div>
            <div>
                <p className={`text-2xs font-semibold uppercase tracking-[0.12em] ${isDark ? 'text-ink-400' : 'text-ink-500 dark:text-ink-400'}`}>
                    {label}
                </p>
                <p className={`text-2xl sm:text-3xl font-semibold tracking-tight mt-1 ${isDark ? 'text-white' : 'text-ink-900 dark:text-white'}`}>
                    {value}
                </p>
                {hint && (
                    <p className={`mt-1 text-xs ${isDark ? 'text-ink-400' : 'text-ink-500 dark:text-ink-400'}`}>{hint}</p>
                )}
                {children}
            </div>
        </Wrapper>
    );
}
