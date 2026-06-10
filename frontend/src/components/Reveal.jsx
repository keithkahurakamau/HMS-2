import React, { useEffect, useRef, useState } from 'react';

/**
 * Reveal — wraps any content and fades it up when it enters the viewport.
 *
 * Why a component (and not a CSS class) — IntersectionObserver gives us
 * a precise trigger so animations only run when the user actually sees
 * the section, and we don't burn render cycles animating off-screen DOM
 * during initial page load. Once revealed, the observer disconnects so
 * scroll-back doesn't re-trigger the animation.
 *
 * Props
 * - delayMs: optional stagger when multiple Reveals sit side-by-side
 * - as:      element type (default 'div'), so headings stay headings
 * - className: pass-through for layout classes
 * - threshold: IntersectionObserver threshold (default 0.15)
 */
export default function Reveal({
    children,
    delayMs = 0,
    as: Tag = 'div',
    className = '',
    threshold = 0.15,
    ...rest
}) {
    const ref = useRef(null);
    // Honour reduced-motion at mount by deriving the initial state, rather than
    // flipping `shown` from inside the effect when a prop changes. If the user
    // prefers reduced motion the content is simply shown straight away.
    const prefersReducedMotion =
        typeof window !== 'undefined' &&
        window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const [shown, setShown] = useState(prefersReducedMotion);

    useEffect(() => {
        if (prefersReducedMotion) return; // already shown — nothing to observe
        const el = ref.current;
        if (!el) return;
        const io = new IntersectionObserver((entries) => {
            entries.forEach((e) => {
                if (e.isIntersecting) {
                    setShown(true);
                    io.disconnect();
                }
            });
        }, { threshold, rootMargin: '0px 0px -8% 0px' });
        io.observe(el);
        return () => io.disconnect();
    }, [threshold, prefersReducedMotion]);

    return (
        <Tag
            ref={ref}
            style={shown ? { animationDelay: `${delayMs}ms` } : undefined}
            className={`${shown ? 'animate-reveal-up' : 'opacity-0'} ${className}`}
            {...rest}
        >
            {children}
        </Tag>
    );
}
