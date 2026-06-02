import React, { useEffect, useRef } from 'react';

/**
 * PremiumBackground — fixed full-viewport layer with multiple animated
 * sources working together so the page never reads as a static white
 * surface.
 *
 *  Composition (top-to-bottom in z-order)
 *  --------------------------------------
 *   • bg-mesh-anim    — three-stop radial gradient on a 200% canvas,
 *                       slides via mesh-shift keyframe. Always-on base
 *                       colour so the page never goes white between
 *                       blob coverage zones.
 *   • Halo            — full-bleed conic gradient (cyan→teal→emerald→
 *                       transparent), rotates with halo-spin (90s loop).
 *                       Gives a quiet, continuous colour wash.
 *   • Three blobs     — radial gradients at fixed anchor points,
 *                       parallax-follow the cursor with damped lerp.
 *   • Particle field  — 14 small glowing dots orbiting on the
 *                       particle-orbit keyframe with twinkle. Wrapped
 *                       in a layer that parallax-shifts with the cursor
 *                       so the field tilts as you move.
 *   • Spotlight       — soft white-cyan disc, plus-lighter blend,
 *                       tracks cursor 1:1.
 *   • Grain           — 32×32 hairline grid texture at 2% opacity for
 *                       "paper" feel.
 *
 *  Performance
 *  -----------
 *   • Every animated property is `transform` or `opacity` — composited,
 *     never triggers layout.
 *   • Single rAF loop in JS mutates refs directly. No React re-renders.
 *   • Particles use plain CSS animation (per-particle inline duration +
 *     delay) so they keep moving even when the JS thread is busy.
 *
 *  Accessibility
 *  -------------
 *   • Honors `prefers-reduced-motion: reduce` — rAF never starts; CSS
 *     animations get neutralised by the universal-selector rule in
 *     index.css.
 *   • `aria-hidden`, `pointer-events: none` throughout.
 */

// Fixed-seed particle positions so the field is stable across renders.
// Each entry: [leftPercent, topPercent, sizePx, hueIndex, orbitDurationSec,
//             orbitDelaySec, twinkleDurationSec, direction].
//   hueIndex 0 = cyan, 1 = teal, 2 = emerald, 3 = brand-soft-white
//   direction 'normal' / 'reverse' breaks lockstep with neighbours
const PARTICLE_HUES = [
    'rgba(34, 211, 238, 0.85)',   // cyan
    'rgba(45, 212, 191, 0.80)',   // teal
    'rgba(110, 231, 183, 0.75)',  // emerald
    'rgba(255, 255, 255, 0.90)',  // bright halo
];
const PARTICLES = [
    [ 8,  18,  6, 0, 22, -3,  3.2, 'normal'],
    [22,  10,  4, 1, 28, -8,  2.4, 'reverse'],
    [38,  22,  8, 2, 26, -2,  3.8, 'normal'],
    [55,  14,  5, 3, 24, -12, 2.8, 'reverse'],
    [72,  28,  7, 0, 30, -6,  3.4, 'normal'],
    [88,  18,  4, 1, 26, -10, 2.6, 'reverse'],
    [12,  48,  6, 2, 28, -4,  3.2, 'normal'],
    [30,  60,  9, 0, 32, -14, 4.0, 'reverse'],
    [48,  52, 10, 3, 30, -8,  3.6, 'normal'],
    [68,  58,  5, 1, 24, -2,  2.4, 'reverse'],
    [82,  46,  7, 2, 28, -6,  3.0, 'normal'],
    [18,  78,  6, 0, 26, -10, 2.8, 'reverse'],
    [42,  84,  8, 3, 30, -4,  3.6, 'normal'],
    [78,  82,  6, 1, 28, -12, 3.2, 'reverse'],
];

export default function PremiumBackground() {
    const wrapperRef = useRef(null);
    const blob1Ref = useRef(null);
    const blob2Ref = useRef(null);
    const blob3Ref = useRef(null);
    const particlesRef = useRef(null);
    const spotlightRef = useRef(null);

    useEffect(() => {
        if (typeof window === 'undefined') return;
        const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        if (reduce) return;

        const blob1 = blob1Ref.current;
        const blob2 = blob2Ref.current;
        const blob3 = blob3Ref.current;
        const particles = particlesRef.current;
        const spot  = spotlightRef.current;
        if (!blob1 || !blob2 || !blob3 || !spot || !particles) return;

        let tx = 0.5, ty = 0.5;  // normalized target
        let mx = 0.5, my = 0.5;  // lerped current
        let raf = 0;
        let vw = window.innerWidth;
        let vh = window.innerHeight;

        const onMove = (e) => {
            tx = e.clientX / vw;
            ty = e.clientY / vh;
        };
        const onTouchMove = (e) => {
            if (e.touches.length === 0) return;
            const t = e.touches[0];
            tx = t.clientX / vw;
            ty = t.clientY / vh;
        };
        const onResize = () => {
            vw = window.innerWidth;
            vh = window.innerHeight;
        };

        const tick = () => {
            mx += (tx - mx) * 0.06;
            my += (ty - my) * 0.06;

            // Blobs parallax (×90 / ×60 inverse / ×35).
            blob1.style.transform = `translate3d(${(mx - 0.5) * 90}px, ${(my - 0.5) * 90}px, 0)`;
            blob2.style.transform = `translate3d(${(0.5 - mx) * 60}px, ${(0.5 - my) * 60}px, 0)`;
            blob3.style.transform = `translate3d(${(mx - 0.5) * 35}px, ${(my - 0.5) * 35}px, 0)`;

            // Particle field parallax — the whole layer shifts subtly so
            // the dots tilt as you move. Per-particle CSS animation keeps
            // running independently.
            particles.style.transform = `translate3d(${(mx - 0.5) * 25}px, ${(my - 0.5) * 25}px, 0)`;

            // Spotlight 1:1 with cursor.
            spot.style.transform = `translate3d(${mx * vw}px, ${my * vh}px, 0) translate(-50%, -50%)`;

            raf = requestAnimationFrame(tick);
        };

        window.addEventListener('mousemove', onMove, { passive: true });
        window.addEventListener('touchmove', onTouchMove, { passive: true });
        window.addEventListener('resize', onResize, { passive: true });
        raf = requestAnimationFrame(tick);

        return () => {
            window.removeEventListener('mousemove', onMove);
            window.removeEventListener('touchmove', onTouchMove);
            window.removeEventListener('resize', onResize);
            cancelAnimationFrame(raf);
        };
    }, []);

    return (
        <div
            ref={wrapperRef}
            aria-hidden="true"
            className="fixed inset-0 -z-10 pointer-events-none overflow-hidden bg-ink-50"
        >
            {/* Static-ish base mesh wash */}
            <div className="absolute inset-0 bg-mesh-anim animate-mesh-shift" />

            {/* Slow-spin conic halo — gives constant background colour
                rotation even when the user isn't moving. 90s/loop so it
                never reads as "spinning," just quietly alive. */}
            <div
                className="absolute -inset-[20%]"
                style={{
                    background: 'conic-gradient(from 0deg at 50% 50%, rgba(34, 211, 238, 0.18) 0%, rgba(45, 212, 191, 0.16) 25%, rgba(110, 231, 183, 0.14) 50%, transparent 65%, rgba(34, 211, 238, 0.18) 100%)',
                    animation: 'halo-spin 90s linear infinite',
                    willChange: 'transform',
                    filter: 'blur(60px)',
                }}
            />

            {/* Parallax blob 1 — cyan, forward parallax */}
            <div
                ref={blob1Ref}
                className="absolute top-[8%] left-[10%] size-[42rem] rounded-full"
                style={{
                    background: 'radial-gradient(circle, rgba(34, 211, 238, 0.45) 0%, rgba(34, 211, 238, 0.12) 30%, transparent 65%)',
                    willChange: 'transform',
                    filter: 'blur(30px)',
                }}
            />
            {/* Parallax blob 2 — teal, inverse parallax */}
            <div
                ref={blob2Ref}
                className="absolute bottom-[8%] right-[8%] size-[38rem] rounded-full"
                style={{
                    background: 'radial-gradient(circle, rgba(45, 212, 191, 0.42) 0%, rgba(45, 212, 191, 0.10) 35%, transparent 70%)',
                    willChange: 'transform',
                    filter: 'blur(30px)',
                }}
            />
            {/* Parallax blob 3 — emerald, slow forward parallax */}
            <div
                ref={blob3Ref}
                className="absolute top-[40%] left-[55%] size-[34rem] rounded-full"
                style={{
                    background: 'radial-gradient(circle, rgba(110, 231, 183, 0.36) 0%, rgba(110, 231, 183, 0.08) 35%, transparent 70%)',
                    willChange: 'transform',
                    filter: 'blur(30px)',
                }}
            />

            {/* Particle field — wrapped in a single layer so the whole
                field can parallax with the cursor without touching each
                particle's individual orbit. */}
            <div ref={particlesRef} className="absolute inset-0" style={{ willChange: 'transform' }}>
                {PARTICLES.map(([left, top, size, hueIdx, dur, delay, twinkleDur, direction], i) => (
                    <span
                        key={i}
                        className="absolute rounded-full block"
                        style={{
                            left: `${left}%`,
                            top: `${top}%`,
                            width: `${size}px`,
                            height: `${size}px`,
                            background: PARTICLE_HUES[hueIdx],
                            boxShadow: `0 0 ${size * 2}px ${PARTICLE_HUES[hueIdx]}, 0 0 ${size * 4}px ${PARTICLE_HUES[hueIdx].replace(/[\d.]+\)$/, '0.3)')}`,
                            animation: `particle-orbit ${dur}s ease-in-out ${delay}s infinite ${direction}, twinkle ${twinkleDur}s ease-in-out ${delay}s infinite`,
                            willChange: 'transform, opacity',
                        }}
                    />
                ))}
            </div>

            {/* Cursor-tracking spotlight */}
            <div
                ref={spotlightRef}
                className="absolute top-0 left-0 size-[60rem] rounded-full"
                style={{
                    background: 'radial-gradient(circle, rgba(255, 255, 255, 0.25) 0%, rgba(34, 211, 238, 0.08) 25%, transparent 55%)',
                    willChange: 'transform',
                    transform: 'translate3d(50vw, 50vh, 0) translate(-50%, -50%)',
                    mixBlendMode: 'plus-lighter',
                }}
            />

            {/* Hairline grid texture overlay — 2.5% opacity "paper" feel */}
            <div
                className="absolute inset-0 opacity-[0.025] mix-blend-multiply"
                style={{
                    backgroundImage:
                        'linear-gradient(rgba(15, 23, 42, 1) 1px, transparent 1px), linear-gradient(90deg, rgba(15, 23, 42, 1) 1px, transparent 1px)',
                    backgroundSize: '32px 32px',
                }}
            />
        </div>
    );
}
