import React, { useEffect, useState, useRef } from 'react';
import { createPortal } from 'react-dom';
import { ChevronLeft, ChevronRight, X, Sparkles, CheckCircle2 } from 'lucide-react';
import { useJourney } from '../context/JourneyContext';

/**
 * JourneyOverlay — full-viewport tour scrim with a moving spotlight
 * cutout that highlights the current step's target element, plus a
 * tooltip card with the step's title/body and Next/Back/Skip controls.
 *
 *   • Spotlight is drawn via SVG `<mask>` so the target element shows
 *     through cleanly even when sitting over the cursor-reactive
 *     background; the rest of the page dims to a 60% slate scrim.
 *   • Tooltip placement is computed from the target's bounding rect
 *     plus the step's `placement` hint; we clamp to viewport edges so
 *     a card never spills off-screen.
 *   • Steps with no `selector` (or an unresolved one) render a centred
 *     card with no spotlight — useful for the "Welcome to <module>"
 *     opening step.
 *   • Pressing Escape skips the current tour.
 *
 * Why no third-party library — driver.js, shepherd.js, intro.js all
 * weigh ~30-60 KB minified and bundle their own theming systems we'd
 * have to fight to match the brand. This component is ~150 LOC and
 * fully owns its look.
 */
export default function JourneyOverlay() {
    const { activeKey, activeSteps, completeCurrent, skipCurrent, skipAll } = useJourney();
    const [stepIdx, setStepIdx] = useState(0);
    const [target, setTarget] = useState(null);  // DOMRect or null
    const cardRef = useRef(null);

    // Reset to first step when the active tour changes.
    useEffect(() => {
        setStepIdx(0);
    }, [activeKey]);

    const step = activeSteps[stepIdx] || null;

    // Resolve target element + watch for scroll/resize so the spotlight
    // tracks even if the page moves underneath it.
    useEffect(() => {
        if (!step) { setTarget(null); return; }
        const update = () => {
            if (!step.selector) { setTarget(null); return; }
            const el = document.querySelector(step.selector);
            if (!el) { setTarget(null); return; }
            // Scroll into view first so spotlight lands somewhere visible.
            el.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'nearest' });
            // Defer the rect read so smooth-scroll has time to settle.
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

    // Escape key skips the tour entirely.
    useEffect(() => {
        if (!activeKey) return;
        const onKey = (e) => { if (e.key === 'Escape') skipCurrent(); };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [activeKey, skipCurrent]);

    if (!activeKey || !step) return null;

    const total = activeSteps.length;
    const isLast = stepIdx === total - 1;
    const isFirst = stepIdx === 0;

    // ── Compute card position ─────────────────────────────────────────
    const PAD = 16;          // gap between target and card
    const CARD_W = 340;
    const CARD_H = 220;      // approx; clamping handles tall content

    let cardStyle;
    if (!target || step.placement === 'center') {
        cardStyle = {
            position: 'fixed',
            top: '50%',
            left: '50%',
            transform: 'translate(-50%, -50%)',
            width: CARD_W,
        };
    } else {
        const placement = step.placement || 'bottom';
        let top = 0, left = 0;
        if (placement === 'bottom') {
            top = target.bottom + PAD;
            left = target.left + target.width / 2 - CARD_W / 2;
        } else if (placement === 'top') {
            top = target.top - CARD_H - PAD;
            left = target.left + target.width / 2 - CARD_W / 2;
        } else if (placement === 'right') {
            top = target.top + target.height / 2 - CARD_H / 2;
            left = target.right + PAD;
        } else if (placement === 'left') {
            top = target.top + target.height / 2 - CARD_H / 2;
            left = target.left - CARD_W - PAD;
        }
        // Clamp to viewport
        left = Math.max(PAD, Math.min(left, window.innerWidth - CARD_W - PAD));
        top = Math.max(PAD, Math.min(top, window.innerHeight - CARD_H - PAD));
        cardStyle = { position: 'fixed', top, left, width: CARD_W };
    }

    // ── Spotlight rectangle (only when we have a target) ──────────────
    const HOLE_PAD = 8;
    const hole = target ? {
        x: target.left - HOLE_PAD,
        y: target.top - HOLE_PAD,
        w: target.width + HOLE_PAD * 2,
        h: target.height + HOLE_PAD * 2,
    } : null;

    return createPortal(
        <div className="fixed inset-0 z-[1000] pointer-events-none" aria-live="polite">
            {/* Backdrop scrim with spotlight cutout */}
            <svg
                className="absolute inset-0 w-full h-full pointer-events-auto"
                style={{ position: 'fixed' }}
                onClick={skipCurrent}
            >
                <defs>
                    <mask id="journey-mask">
                        <rect x="0" y="0" width="100%" height="100%" fill="white" />
                        {hole && (
                            <rect
                                x={hole.x}
                                y={hole.y}
                                width={hole.w}
                                height={hole.h}
                                rx="12"
                                fill="black"
                            />
                        )}
                    </mask>
                </defs>
                <rect
                    x="0"
                    y="0"
                    width="100%"
                    height="100%"
                    fill="rgba(15, 23, 42, 0.65)"
                    mask="url(#journey-mask)"
                />
                {hole && (
                    <rect
                        x={hole.x}
                        y={hole.y}
                        width={hole.w}
                        height={hole.h}
                        rx="12"
                        fill="none"
                        stroke="rgba(34, 211, 238, 0.85)"
                        strokeWidth="2"
                    />
                )}
            </svg>

            {/* Tooltip card */}
            <div
                ref={cardRef}
                style={cardStyle}
                className="pointer-events-auto rounded-2xl bg-white shadow-elevated ring-1 ring-ink-200/70 p-5 animate-fade-in"
                role="dialog"
                aria-label={step.title}
            >
                <div className="flex items-start justify-between gap-3 mb-3">
                    <div className="flex items-center gap-2">
                        <span className="w-7 h-7 rounded-lg bg-gradient-to-br from-brand-500 to-teal-500 text-white flex items-center justify-center shrink-0">
                            <Sparkles size={14} />
                        </span>
                        <span className="text-2xs font-semibold uppercase tracking-[0.14em] text-ink-500">
                            Step {stepIdx + 1} of {total}
                        </span>
                    </div>
                    <button
                        type="button"
                        onClick={skipCurrent}
                        aria-label="Skip this tour"
                        className="p-1 rounded-md text-ink-400 hover:text-ink-700 hover:bg-ink-100 transition-colors cursor-pointer"
                    >
                        <X size={16} />
                    </button>
                </div>

                <h3 className="text-base font-semibold text-ink-900 tracking-tight">{step.title}</h3>
                <p className="mt-1.5 text-sm text-ink-600 leading-relaxed">{step.body}</p>

                {/* Progress dots */}
                <div className="mt-4 flex items-center gap-1.5" aria-hidden="true">
                    {activeSteps.map((_, i) => (
                        <span
                            key={i}
                            className={`h-1.5 rounded-full transition-all ${
                                i === stepIdx ? 'w-6 bg-brand-600' : 'w-1.5 bg-ink-200'
                            }`}
                        />
                    ))}
                </div>

                {/* Controls */}
                <div className="mt-4 flex items-center justify-between gap-2">
                    <button
                        type="button"
                        onClick={skipAll}
                        className="text-xs font-medium text-ink-500 hover:text-ink-900 transition-colors cursor-pointer"
                    >
                        Skip all tours
                    </button>
                    <div className="flex items-center gap-2">
                        {!isFirst && (
                            <button
                                type="button"
                                onClick={() => setStepIdx(i => Math.max(0, i - 1))}
                                className="btn-secondary text-xs px-3 py-1.5"
                            >
                                <ChevronLeft size={13} /> Back
                            </button>
                        )}
                        {!isLast ? (
                            <button
                                type="button"
                                onClick={() => setStepIdx(i => Math.min(total - 1, i + 1))}
                                className="btn-primary text-xs px-3 py-1.5"
                            >
                                Next <ChevronRight size={13} />
                            </button>
                        ) : (
                            <button
                                type="button"
                                onClick={completeCurrent}
                                className="btn-primary text-xs px-3 py-1.5"
                            >
                                <CheckCircle2 size={13} /> Got it
                            </button>
                        )}
                    </div>
                </div>
            </div>
        </div>,
        document.body
    );
}
