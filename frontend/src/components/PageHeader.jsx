import React from 'react';

/**
 * PageHeader — the uniform header surface every page in the workspace renders.
 *
 *  Why this component exists
 *  -------------------------
 *  Pages in HMS-2 used to roll their own header markup, which meant the
 *  eyebrow/title/subtitle ratio drifted from page to page and primary
 *  actions floated in inconsistent positions. This component locks the
 *  pattern so the design stays coherent as new pages get added.
 *
 *  Anatomy
 *  -------
 *  ┌──────────────────────────────────────────────────────────────┐
 *  │  EYEBROW                                                     │
 *  │  ●  Title                            [ actions ............ ]│
 *  │  Subtitle                                                    │
 *  └──────────────────────────────────────────────────────────────┘
 *
 *  - eyebrow:   Section context (department / module). Optional.
 *  - icon:      Lucide icon component, rendered inside a tinted chip.
 *  - title:     Main page title.
 *  - subtitle:  One-line description. Optional.
 *  - meta:      Right-side info chip (e.g. "Last sync 12s ago"). Optional.
 *  - actions:   Right-side action buttons (use .btn-* classes). Optional.
 *  - tone:      brand | teal | accent | neutral | warning. Affects icon chip
 *               and eyebrow accent.
 */
export default function PageHeader({
    eyebrow,
    icon: Icon,
    title,
    subtitle,
    meta,
    actions,
    tone = 'brand',
    surface = 'light',
}) {
    const lightTones = {
        brand:   { chip: 'bg-brand-50 text-brand-700 ring-brand-100',     eyebrow: 'text-brand-700' },
        teal:    { chip: 'bg-teal-50 text-teal-700 ring-teal-100',        eyebrow: 'text-teal-700' },
        accent:  { chip: 'bg-accent-50 text-accent-700 ring-accent-100',  eyebrow: 'text-accent-700' },
        neutral: { chip: 'bg-ink-100 text-ink-700 ring-ink-200',          eyebrow: 'text-ink-500' },
        warning: { chip: 'bg-amber-50 text-amber-700 ring-amber-100',     eyebrow: 'text-amber-700' },
        rose:    { chip: 'bg-rose-50 text-rose-700 ring-rose-100',        eyebrow: 'text-rose-700' },
    };
    // On dark surfaces (the superadmin console) we keep the same hue family
    // but pull the chip backgrounds to translucent overlays so they read
    // crisply on ink-950. Eyebrow lifts to the lighter shade of the same hue.
    const darkTones = {
        brand:   { chip: 'bg-brand-500/10 text-brand-300 ring-brand-500/20', eyebrow: 'text-brand-300' },
        teal:    { chip: 'bg-teal-500/10 text-teal-300 ring-teal-500/20',    eyebrow: 'text-teal-300' },
        accent:  { chip: 'bg-accent-500/10 text-accent-300 ring-accent-500/20', eyebrow: 'text-accent-300' },
        neutral: { chip: 'bg-white/[0.06] text-ink-200 ring-white/10',       eyebrow: 'text-ink-400' },
        warning: { chip: 'bg-amber-500/10 text-amber-300 ring-amber-500/20', eyebrow: 'text-amber-300' },
        rose:    { chip: 'bg-rose-500/10 text-rose-300 ring-rose-500/20',    eyebrow: 'text-rose-300' },
    };
    const isDark = surface === 'dark';
    const t = (isDark ? darkTones : lightTones)[tone] || (isDark ? darkTones : lightTones).brand;

    return (
        <header className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between mb-6">
            <div className="flex items-start gap-4 min-w-0">
                {Icon && (
                    <div className={`shrink-0 w-12 h-12 rounded-2xl flex items-center justify-center ring-1 ring-inset ${t.chip}`}>
                        <Icon size={20} />
                    </div>
                )}
                <div className="min-w-0">
                    {eyebrow && (
                        <span className={`text-2xs font-semibold uppercase tracking-[0.16em] ${t.eyebrow}`}>
                            {eyebrow}
                        </span>
                    )}
                    <h1 className={`mt-0.5 text-xl sm:text-2xl font-semibold tracking-tight leading-tight ${
                        isDark ? 'text-white' : 'text-ink-900 dark:text-white'
                    }`}>
                        {title}
                    </h1>
                    {subtitle && (
                        <p className={`mt-1 text-sm max-w-2xl leading-relaxed ${
                            isDark ? 'text-ink-400' : 'text-ink-500'
                        }`}>
                            {subtitle}
                        </p>
                    )}
                </div>
            </div>
            {(actions || meta) && (
                <div className="flex items-center gap-2 flex-wrap">
                    {meta}
                    {actions}
                </div>
            )}
        </header>
    );
}
