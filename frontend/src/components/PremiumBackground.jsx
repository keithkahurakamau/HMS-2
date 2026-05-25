import React, { useEffect, useRef } from 'react';

/**
 * PremiumBackground — fixed full-viewport layer that gently follows the
 * user's cursor.
 *
 *  Three drifting gradient blobs (cyan, teal, emerald) sit at fixed
 *  anchor points and translate toward the cursor with different
 *  parallax intensities — fast / slow-inverse / very-slow — so the
 *  composition feels alive rather than choreographed. A fourth
 *  "spotlight" disc travels with the cursor 1:1 to add the impression
 *  of a soft light source moving across the page.
 *
 *  Mechanics
 *  --------
 *   • mousemove sets a *target* position; an rAF loop lerps the
 *     *current* position toward it (damping factor 0.06). That
 *     decouples input rate from render rate so iOS Safari and
 *     low-DPI Chrome both stay smooth.
 *   • Updates only mutate `transform: translate3d(...)` on the four
 *     children — GPU-composited, never triggers layout/paint.
 *   • `will-change: transform` is set explicitly so the browser keeps
 *     the layers on their own compositor planes.
 *
 *  Accessibility
 *  -------------
 *   • Honors `prefers-reduced-motion: reduce` — the rAF loop never
 *     starts; the layer stays at its idle composition.
 *   • `aria-hidden`, `pointer-events: none` — never blocks clicks
 *     or interferes with screen readers.
 */
export default function PremiumBackground() {
    const wrapperRef = useRef(null);
    const blob1Ref = useRef(null);
    const blob2Ref = useRef(null);
    const blob3Ref = useRef(null);
    const spotlightRef = useRef(null);

    useEffect(() => {
        if (typeof window === 'undefined') return;
        const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        if (reduce) return;

        const blob1 = blob1Ref.current;
        const blob2 = blob2Ref.current;
        const blob3 = blob3Ref.current;
        const spot  = spotlightRef.current;
        if (!blob1 || !blob2 || !blob3 || !spot) return;

        // Normalized cursor target (0..1). Initial centre so the very
        // first frame doesn't snap from the corner.
        let tx = 0.5, ty = 0.5;
        // Current lerped value — the actual position the blobs render at.
        let mx = 0.5, my = 0.5;
        let raf = 0;

        // Cache viewport size — recomputed on resize. Avoids reading
        // `window.innerWidth/Height` 60 times per second.
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
            // Critically damped lerp toward the cursor target.
            mx += (tx - mx) * 0.06;
            my += (ty - my) * 0.06;

            // Blob 1: forward parallax (follows cursor strongly)
            const b1x = (mx - 0.5) * 90;
            const b1y = (my - 0.5) * 90;
            blob1.style.transform = `translate3d(${b1x}px, ${b1y}px, 0)`;

            // Blob 2: inverse parallax (moves opposite to cursor, gentler)
            const b2x = (0.5 - mx) * 60;
            const b2y = (0.5 - my) * 60;
            blob2.style.transform = `translate3d(${b2x}px, ${b2y}px, 0)`;

            // Blob 3: slow forward parallax (barely follows)
            const b3x = (mx - 0.5) * 35;
            const b3y = (my - 0.5) * 35;
            blob3.style.transform = `translate3d(${b3x}px, ${b3y}px, 0)`;

            // Spotlight: tracks 1:1 with cursor. The disc is centred on
            // its own midpoint via initial translate(-50%, -50%); we
            // add the cursor offset on top.
            const spotX = mx * vw;
            const spotY = my * vh;
            spot.style.transform = `translate3d(${spotX}px, ${spotY}px, 0) translate(-50%, -50%)`;

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
            {/* Static base radial mesh — provides the colour wash even when
                the cursor isn't moving. Sits underneath the parallax blobs
                so the page never goes "white" between blob layers. */}
            <div className="absolute inset-0 bg-mesh-anim animate-mesh-shift" />

            {/* Parallax blob 1 — cyan, forward parallax */}
            <div
                ref={blob1Ref}
                className="absolute top-[8%] left-[10%] w-[42rem] h-[42rem] rounded-full"
                style={{
                    background: 'radial-gradient(circle, rgba(34, 211, 238, 0.22) 0%, rgba(34, 211, 238, 0.06) 35%, transparent 65%)',
                    willChange: 'transform',
                    filter: 'blur(40px)',
                }}
            />

            {/* Parallax blob 2 — teal, inverse parallax */}
            <div
                ref={blob2Ref}
                className="absolute bottom-[10%] right-[8%] w-[38rem] h-[38rem] rounded-full"
                style={{
                    background: 'radial-gradient(circle, rgba(45, 212, 191, 0.20) 0%, rgba(45, 212, 191, 0.05) 40%, transparent 70%)',
                    willChange: 'transform',
                    filter: 'blur(40px)',
                }}
            />

            {/* Parallax blob 3 — emerald, slow forward parallax */}
            <div
                ref={blob3Ref}
                className="absolute top-[45%] left-[55%] w-[34rem] h-[34rem] rounded-full"
                style={{
                    background: 'radial-gradient(circle, rgba(110, 231, 183, 0.16) 0%, rgba(110, 231, 183, 0.04) 40%, transparent 70%)',
                    willChange: 'transform',
                    filter: 'blur(40px)',
                }}
            />

            {/* Cursor-tracking spotlight — soft white-cyan radial that
                follows 1:1. translate(-50%,-50%) centres the disc on the
                cursor; the rAF loop adds the cursor offset on top. */}
            <div
                ref={spotlightRef}
                className="absolute top-0 left-0 w-[60rem] h-[60rem] rounded-full"
                style={{
                    background: 'radial-gradient(circle, rgba(255, 255, 255, 0.18) 0%, rgba(34, 211, 238, 0.06) 25%, transparent 55%)',
                    willChange: 'transform',
                    transform: 'translate3d(50vw, 50vh, 0) translate(-50%, -50%)',
                    mixBlendMode: 'plus-lighter',
                }}
            />

            {/* Hairline grid texture overlay — adds a tiny bit of "paper" so
                the surface doesn't look digitally flat. Keep at very low
                opacity so it never competes with content. */}
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
