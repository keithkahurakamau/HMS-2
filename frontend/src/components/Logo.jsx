import React from 'react';

/**
 * MediFleet Logo — a stylized "M" formed from two interlocking caduceus-like
 * arcs, evoking continuity of care and the cyan→teal→emerald medical sweep.
 *
 * Variants:
 *   - "mark"  — just the symbol, square aspect ratio
 *   - "full"  — symbol + wordmark, default
 *   - "wordmark" — text only
 *
 * Tones:
 *   - "color" — gradient + accent stop (default)
 *   - "mono-light" — single-tone white (use on dark surfaces)
 *   - "mono-dark"  — single-tone ink (use on light surfaces)
 *
 * The mark is a pure SVG so it scales crisp at any size and respects
 * `currentColor` for mono variants.
 */
export default function Logo({
    variant = 'full',
    tone = 'color',
    size = 36,
    label = 'MediFleet',
    sublabel,
    className = '',
}) {
    const showWord = variant === 'full' || variant === 'wordmark';
    const showMark = variant === 'full' || variant === 'mark';

    return (
        <div className={`inline-flex items-center gap-3 ${className}`}>
            {showMark && <LogoMark tone={tone} size={size} />}
            {showWord && (
                <div className="flex flex-col leading-none">
                    <span
                        className={`font-semibold tracking-tight ${
                            tone === 'mono-light' ? 'text-white'
                          : tone === 'mono-dark'  ? 'text-ink-900'
                          : 'text-gradient-brand'
                        }`}
                        style={{ fontSize: size * 0.62 }}
                    >
                        {label}
                    </span>
                    {sublabel && (
                        <span
                            className={`mt-1 text-2xs font-semibold uppercase tracking-[0.2em] ${
                                tone === 'mono-light' ? 'text-white/70' : 'text-ink-400'
                            }`}
                        >
                            {sublabel}
                        </span>
                    )}
                </div>
            )}
        </div>
    );
}

function LogoMark({ tone = 'color', size = 36 }) {
    const id = React.useId();
    const gradId = `lg-${id}`;
    const accentId = `lg-acc-${id}`;
    const glowId = `lg-glow-${id}`;

    if (tone === 'mono-light' || tone === 'mono-dark') {
        const fill = tone === 'mono-light' ? '#ffffff' : '#0f172a';
        return (
            <svg width={size} height={size} viewBox="0 0 48 48" fill="none" aria-hidden="true">
                <rect x="2" y="2" width="44" height="44" rx="12" fill={fill} fillOpacity="0.1" />
                <MarkPaths fill={fill} cross={fill} />
            </svg>
        );
    }

    return (
        <svg width={size} height={size} viewBox="0 0 48 48" fill="none" aria-hidden="true">
            <defs>
                <linearGradient id={gradId} x1="0" y1="0" x2="48" y2="48" gradientUnits="userSpaceOnUse">
                    <stop offset="0%" stopColor="#22d3ee" />
                    <stop offset="55%" stopColor="#14b8a6" />
                    <stop offset="100%" stopColor="#10b981" />
                </linearGradient>
                <linearGradient id={accentId} x1="0" y1="0" x2="0" y2="48" gradientUnits="userSpaceOnUse">
                    <stop offset="0%" stopColor="#ffffff" stopOpacity="0.95" />
                    <stop offset="100%" stopColor="#ffffff" stopOpacity="0.75" />
                </linearGradient>
                <filter id={glowId} x="-20%" y="-20%" width="140%" height="140%">
                    <feGaussianBlur stdDeviation="0.6" />
                </filter>
            </defs>
            {/* Rounded backdrop */}
            <rect x="0" y="0" width="48" height="48" rx="13" fill={`url(#${gradId})`} />
            {/* Subtle inner highlight */}
            <rect x="0.5" y="0.5" width="47" height="47" rx="12.5" stroke="#ffffff" strokeOpacity="0.18" />
            <MarkPaths fill={`url(#${accentId})`} cross="#ffffff" />
        </svg>
    );
}

/* The interlocking M / cross / pulse mark — drawn once, reused by every tone. */
function MarkPaths({ fill, cross }) {
    return (
        <g>
            {/* Stylized M arches */}
            <path
                d="M11 35 L11 16 Q11 13 14 13 Q17 13 18.5 15.5 L24 24 L29.5 15.5 Q31 13 34 13 Q37 13 37 16 L37 35"
                stroke={fill}
                strokeWidth="3.2"
                strokeLinecap="round"
                strokeLinejoin="round"
                fill="none"
            />
            {/* Medical cross — the breath in the middle */}
            <g transform="translate(24 24)">
                <rect x="-1.6" y="-5" width="3.2" height="10" rx="1.4" fill={cross} fillOpacity="0.95" />
                <rect x="-5" y="-1.6" width="10" height="3.2" rx="1.4" fill={cross} fillOpacity="0.95" />
            </g>
            {/* Pulse dot — bottom-right energy */}
            <circle cx="37" cy="35" r="2" fill={cross} fillOpacity="0.95" />
        </g>
    );
}

/**
 * TenantLogo — renders the tenant's uploaded logo when present, otherwise
 * falls back to the MediFleet mark. Use anywhere in tenant-scoped surfaces.
 */
export function TenantLogo({
    src,
    fallbackLabel = 'Hospital',
    sublabel,
    size = 40,
    tone = 'color',
    className = '',
}) {
    if (src) {
        return (
            <div className={`inline-flex items-center gap-3 ${className}`}>
                <div
                    className="rounded-xl overflow-hidden bg-white ring-1 ring-ink-200/70 shadow-soft flex items-center justify-center"
                    style={{ width: size, height: size }}
                >
                    <img src={src} alt={fallbackLabel} className="w-full h-full object-contain" />
                </div>
                {fallbackLabel && (
                    <div className="flex flex-col leading-none">
                        {sublabel && (
                            <span
                                className={`text-2xs font-semibold uppercase tracking-[0.18em] ${
                                    tone === 'mono-light' ? 'text-white/70' : 'text-ink-400'
                                }`}
                            >
                                {sublabel}
                            </span>
                        )}
                        <span
                            className={`text-sm font-semibold tracking-tight mt-1 ${
                                tone === 'mono-light' ? 'text-white' : 'text-ink-900'
                            }`}
                        >
                            {fallbackLabel}
                        </span>
                    </div>
                )}
            </div>
        );
    }
    return (
        <Logo variant="full" tone={tone} size={size} label={fallbackLabel} sublabel={sublabel} className={className} />
    );
}
