import React, { useEffect, useState, useMemo } from 'react';
import { createPortal } from 'react-dom';
import {
    ChevronLeft, ChevronRight, X, CheckCircle2,
    ArrowUp, ArrowDown, ArrowLeft, ArrowRight, Compass,
} from 'lucide-react';
import { useJourney } from '../context/JourneyContext';

/**
 * JourneyOverlay: full-viewport guided-tour overlay.
 *
 * Composition (top-to-bottom in z-order)
 *   1. Backdrop scrim with SVG-masked rectangular cutout around the
 *      current step's target element. Click outside the spotlight
 *      skips the tour. Spotlight has a pulsing gradient ring so it
 *      reads as "look here, not just a box of light."
 *   2. Arrow connector: a small circle with a directional glyph
 *      pointing from the tooltip toward the target.
 *   3. Glass tooltip card: gradient outer frame (1.5px brand→teal→
 *      accent), then glass-card body, step counter pill, title with
 *      sparkle icon, optional "tip" annotation in a tinted box,
 *      progress dots (active step has a wide gradient pill, completed
 *      steps a smaller brand dot), Back/Next/Got-it controls,
 *      Skip-all-tours link.
 *
 * Steps with `placement: 'center'` or an unresolved selector render
 * a centred card with no spotlight or arrow, used for "Welcome to …"
 * opening cards and any step whose target may not exist for a given
 * role.
 */
const ARROW_GLYPHS = { up: ArrowUp, down: ArrowDown, left: ArrowLeft, right: ArrowRight };
function ArrowGlyph({ dir }) {
    const Icon = ARROW_GLYPHS[dir] || ArrowUp;
    return <Icon size={16} className="text-brand-600" strokeWidth={2.5} />;
}

export default function JourneyOverlay() {
    const { activeKey, activeSteps, completeCurrent, skipCurrent, skipAll } = useJourney();
    const [stepIdx, setStepIdx] = useState(0);
    const [target, setTarget] = useState(null);  // DOMRect or null

    useEffect(() => { setStepIdx(0); }, [activeKey]);

    const step = activeSteps[stepIdx] || null;

    // Cleanup exists: the cleanup removes every listener it adds.
    // react-doctor-disable-next-line react-doctor/effect-needs-cleanup
    useEffect(() => {
        if (!step) { setTarget(null); return; }
        const update = () => {
            if (!step.selector) { setTarget(null); return; }
            const el = document.querySelector(step.selector);
            if (!el) { setTarget(null); return; }
            el.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'nearest' });
            setTimeout(() => {
                if (!el.isConnected) return;
                setTarget(el.getBoundingClientRect());
            }, 360);
        };
        update();
        window.addEventListener('scroll', update, { passive: true });
        window.addEventListener('resize', update, { passive: true });
        return () => {
            window.removeEventListener('scroll', update);
            window.removeEventListener('resize', update);
        };
    }, [step]);

    useEffect(() => {
        if (!activeKey) return;
        const onKey = (e) => { if (e.key === 'Escape') skipCurrent(); };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [activeKey, skipCurrent]);

    const layout = useMemo(() => {
        const PAD = 22;
        const CARD_W = 360;
        const EST_H = 260;
        if (!target || step?.placement === 'center') {
            return {
                cardStyle: {
                    position: 'fixed', top: '50%', left: '50%',
                    transform: 'translate(-50%, -50%)', width: CARD_W,
                },
                arrow: null,
            };
        }
        const placement = step?.placement || 'bottom';
        let top = 0, left = 0, arrow = null;
        if (placement === 'bottom') {
            top = target.bottom + PAD;
            left = target.left + target.width / 2 - CARD_W / 2;
            arrow = { dir: 'up', x: target.left + target.width / 2, y: top - 12 };
        } else if (placement === 'top') {
            top = target.top - EST_H - PAD;
            left = target.left + target.width / 2 - CARD_W / 2;
            arrow = { dir: 'down', x: target.left + target.width / 2, y: top + EST_H + 4 };
        } else if (placement === 'right') {
            top = target.top + target.height / 2 - EST_H / 2;
            left = target.right + PAD;
            arrow = { dir: 'left', x: left - 12, y: target.top + target.height / 2 };
        } else if (placement === 'left') {
            top = target.top + target.height / 2 - EST_H / 2;
            left = target.left - CARD_W - PAD;
            arrow = { dir: 'right', x: left + CARD_W + 4, y: target.top + target.height / 2 };
        }
        const clampedLeft = Math.max(16, Math.min(left, window.innerWidth - CARD_W - 16));
        const clampedTop = Math.max(16, Math.min(top, window.innerHeight - EST_H - 16));
        return {
            cardStyle: { position: 'fixed', top: clampedTop, left: clampedLeft, width: CARD_W },
            arrow,
        };
    }, [target, step?.placement]);

    if (!activeKey || !step) return null;

    const total = activeSteps.length;
    const isLast = stepIdx === total - 1;
    const isFirst = stepIdx === 0;

    const HOLE_PAD = 10;
    const hole = target ? {
        x: target.left - HOLE_PAD,
        y: target.top - HOLE_PAD,
        w: target.width + HOLE_PAD * 2,
        h: target.height + HOLE_PAD * 2,
    } : null;

    return createPortal(
        <div className="fixed inset-0 z-[1000] pointer-events-none" aria-live="polite">
            {/* Backdrop with masked cutout */}
            <svg
                className="absolute inset-0 w-full h-full pointer-events-auto"
                style={{ position: 'fixed' }}
                onClick={skipCurrent}
                aria-hidden="true"
            >
                <defs>
                    <mask id="journey-mask">
                        <rect x="0" y="0" width="100%" height="100%" fill="white" />
                        {hole && (
                            <rect x={hole.x} y={hole.y} width={hole.w} height={hole.h}
                                  rx="14" fill="black" />
                        )}
                    </mask>
                    <linearGradient id="journey-ring" x1="0" y1="0" x2="1" y2="1">
                        <stop offset="0%" stopColor="rgba(34, 211, 238, 0.95)" />
                        <stop offset="50%" stopColor="rgba(45, 212, 191, 0.85)" />
                        <stop offset="100%" stopColor="rgba(110, 231, 183, 0.75)" />
                    </linearGradient>
                </defs>
                <rect x="0" y="0" width="100%" height="100%"
                      fill="rgba(15, 23, 42, 0.65)" mask="url(#journey-mask)" />
            </svg>

            {/* Pulsing spotlight ring */}
            {hole && (
                <svg
                    style={{
                        position: 'fixed',
                        left: hole.x - 6, top: hole.y - 6,
                        width: hole.w + 12, height: hole.h + 12,
                    }}
                    className="pointer-events-none"
                    aria-hidden="true"
                >
                    <rect x="2" y="2" width={hole.w + 8} height={hole.h + 8}
                          rx="16" fill="none"
                          stroke="url(#journey-ring)" strokeWidth="2.5"
                          className="animate-pulse-soft" />
                </svg>
            )}

            {/* Arrow connector */}
            {layout.arrow && (
                <div
                    className="pointer-events-none"
                    style={{
                        position: 'fixed',
                        left: layout.arrow.x - 14,
                        top: layout.arrow.y - 14,
                    }}
                >
                    <div className="size-7 rounded-full bg-white shadow-overlay ring-2 ring-brand-300/70 flex items-center justify-center animate-pulse-soft">
                        <ArrowGlyph dir={layout.arrow.dir} />
                    </div>
                </div>
            )}

            {/* Tooltip card */}
            <div
                style={layout.cardStyle}
                className="pointer-events-auto rounded-2xl overflow-hidden animate-slide-up"
                role="dialog"
                aria-label={step.title}
            >
                <div className="overlay-surface overflow-hidden">
                    {/* Progress reads as one continuous bar rather than a row of
                        dots: with eight-step tours the dots became noise, and a
                        bar says how far along you are at a glance. */}
                    <div className="h-1 w-full bg-ink-100 dark:bg-ink-800" aria-hidden="true">
                        <div
                            className="h-full bg-brand-600 dark:bg-brand-400"
                            style={{
                                width: `${((stepIdx + 1) / total) * 100}%`,
                                transition: 'width var(--dur-slow) var(--ease-out)',
                            }}
                        />
                    </div>

                    <div className="p-5">
                        <div className="flex items-start justify-between gap-3">
                            <p className="flex items-center gap-2 font-mono text-[10px] font-semibold uppercase tracking-[0.18em] text-brand-700 dark:text-brand-300">
                                <Compass size={13} aria-hidden="true" />
                                Guided tour
                                <span className="text-ink-400 dark:text-ink-500" aria-hidden="true">/</span>
                                <span className="tnum text-ink-500 dark:text-ink-400">
                                    {stepIdx + 1} of {total}
                                </span>
                            </p>
                            <button
                                type="button"
                                onClick={skipCurrent}
                                aria-label="Skip this tour"
                                className="-m-1 p-1 rounded-md text-ink-400 hover:text-ink-700 hover:bg-ink-100 dark:text-ink-500 dark:hover:text-ink-200 dark:hover:bg-ink-800 transition-colors cursor-pointer"
                            >
                                <X size={16} />
                            </button>
                        </div>

                        <h3 className="mt-3 text-[1.0625rem] font-semibold leading-snug tracking-tight text-ink-900 dark:text-ink-100 text-balance">
                            {step.title}
                        </h3>
                        <p className="mt-1.5 text-sm leading-relaxed text-ink-600 dark:text-ink-300">
                            {step.body}
                        </p>

                        {step.tip && (
                            <p className="mt-3 rounded-lg border-l-2 border-brand-500 bg-brand-50 dark:bg-brand-500/10 px-3 py-2 text-xs text-brand-800 dark:text-brand-200">
                                <span className="font-semibold">Tip: </span>{step.tip}
                            </p>
                        )}

                        <div className="mt-5 flex items-center justify-between gap-2 border-t border-ink-100 dark:border-ink-800 pt-3">
                            <button
                                type="button"
                                onClick={skipAll}
                                className="text-xs font-medium text-ink-500 dark:text-ink-400 hover:text-ink-900 dark:hover:text-ink-100 transition-colors cursor-pointer"
                            >
                                Skip all tours
                            </button>
                            <div className="flex items-center gap-2">
                                {!isFirst && (
                                    <button
                                        type="button"
                                        onClick={() => setStepIdx(i => Math.max(0, i - 1))}
                                        className="btn btn-secondary btn-xs"
                                    >
                                        <ChevronLeft size={13} /> Back
                                    </button>
                                )}
                                {!isLast ? (
                                    <button
                                        type="button"
                                        onClick={() => setStepIdx(i => Math.min(total - 1, i + 1))}
                                        className="btn btn-primary btn-xs"
                                    >
                                        Next <ChevronRight size={13} />
                                    </button>
                                ) : (
                                    <button
                                        type="button"
                                        onClick={completeCurrent}
                                        className="btn btn-primary btn-xs"
                                    >
                                        <CheckCircle2 size={13} /> Got it
                                    </button>
                                )}
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>,
        document.body
    );
}
