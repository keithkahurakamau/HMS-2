import React, { useEffect, useRef, useState } from 'react';

/**
 * CountUp — animated integer that ticks 0 → `to` once the element scrolls
 * into view (40% visibility). Uses IntersectionObserver so we don't burn
 * requestAnimationFrame cycles on counters the user will never see.
 * Snaps to `to` immediately when prefers-reduced-motion is set.
 *
 * Props
 * - to: target number
 * - suffix: optional string appended after the count (e.g. '%', '+')
 * - durationMs: animation duration; cubic ease-out for a satisfying decel
 */
export default function CountUp({ to, suffix = '', durationMs = 1100 }) {
    const [value, setValue] = useState(0);
    const ref = useRef(null);
    const startedRef = useRef(false);

    useEffect(() => {
        if (typeof window === 'undefined') return;
        const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        if (reduce) { setValue(to); return; }

        const el = ref.current;
        if (!el) return;
        const io = new IntersectionObserver((entries) => {
            entries.forEach((e) => {
                if (!e.isIntersecting || startedRef.current) return;
                startedRef.current = true;
                const start = performance.now();
                const tick = (now) => {
                    const t = Math.min(1, (now - start) / durationMs);
                    const eased = 1 - Math.pow(1 - t, 3);
                    setValue(Math.round(eased * to));
                    if (t < 1) requestAnimationFrame(tick);
                };
                requestAnimationFrame(tick);
            });
        }, { threshold: 0.4 });
        io.observe(el);
        return () => io.disconnect();
    }, [to, durationMs]);

    return <span ref={ref} className="tabular-nums">{value}{suffix}</span>;
}
