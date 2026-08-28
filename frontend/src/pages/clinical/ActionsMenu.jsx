import React, { useState, useRef, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { ChevronDown } from 'lucide-react';

const PANEL_W = 256;   // w-64
const MARGIN = 8;      // keep this far from the viewport edge
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

/**
 * Consolidated "Actions ▾" bubble for the DoctorV2 clinical desk. Grouped,
 * permission-gated items (items the user can't use are hidden; empty groups
 * disappear). The popover is portaled to <body> so it escapes the workspace's
 * overflow/stacking context, is clamped to the viewport, flips above the
 * trigger when there's no room below, and points back at the button with a
 * little caret.
 *
 * groups: [{ label, items: [{ label, icon, onClick, perm?, disabled? }] }]
 * has:    (perm) => boolean
 */
export default function ActionsMenu({ groups, has, disabled = false }) {
    const [open, setOpen] = useState(false);
    const [shown, setShown] = useState(false); // drives the pop-in transition
    const [pos, setPos] = useState(null);
    const btnRef = useRef(null);
    const menuRef = useRef(null);

    // Single pass: drop items the user can't use, then drop empty groups.
    const visibleGroups = groups.reduce((acc, g) => {
        const items = g.items.filter((it) => !it.perm || has(it.perm));
        if (items.length) acc.push({ ...g, items });
        return acc;
    }, []);

    const place = useCallback(() => {
        const r = btnRef.current?.getBoundingClientRect();
        if (!r) return;
        const spaceBelow = window.innerHeight - r.bottom;
        const flip = spaceBelow < 320 && r.top > spaceBelow; // not enough room below → open upward
        // Right-align the panel to the trigger, then keep it on-screen.
        const right = clamp(window.innerWidth - r.right, MARGIN, window.innerWidth - PANEL_W - MARGIN);
        // Caret sits under the trigger's centre, measured from the panel's right edge.
        const panelRightX = window.innerWidth - right;
        const caretRight = clamp(panelRightX - (r.left + r.width / 2) - 6, 14, PANEL_W - 26);
        setPos({
            right,
            caretRight,
            flip,
            top: flip ? undefined : r.bottom + 10,
            bottom: flip ? window.innerHeight - r.top + 10 : undefined,
        });
    }, []);

    useEffect(() => {
        if (!open) return undefined;
        // Position is measured in the click handler before opening (a DOM read,
        // not effect state): here we just animate in and track viewport changes.
        const raf = requestAnimationFrame(() => setShown(true));
        const onDoc = (e) => {
            if (menuRef.current?.contains(e.target) || btnRef.current?.contains(e.target)) return;
            setOpen(false);
        };
        const onKey = (e) => { if (e.key === 'Escape') setOpen(false); };
        document.addEventListener('mousedown', onDoc);
        document.addEventListener('keydown', onKey);
        window.addEventListener('resize', place);
        window.addEventListener('scroll', place, true);
        return () => {
            cancelAnimationFrame(raf);
            document.removeEventListener('mousedown', onDoc);
            document.removeEventListener('keydown', onKey);
            window.removeEventListener('resize', place);
            window.removeEventListener('scroll', place, true);
        };
    }, [open, place]);

    if (visibleGroups.length === 0) return null;

    const caretStyle = { right: pos?.caretRight, [pos?.flip ? 'bottom' : 'top']: -5 };

    return (
        <>
            <button ref={btnRef} type="button" disabled={disabled}
                onClick={() => { if (!open) { place(); setShown(false); } setOpen((o) => !o); }}
                aria-haspopup="menu" aria-expanded={open}
                className={`btn-secondary text-sm gap-1.5 ${open ? 'ring-2 ring-brand-500/30 border-brand-300 dark:border-brand-500/40' : ''}`}>
                Actions <ChevronDown size={15} className={`transition-transform ${open ? 'rotate-180' : ''}`} />
            </button>
            {open && pos && createPortal(
                <div ref={menuRef} role="menu"
                    style={{ position: 'fixed', top: pos.top, bottom: pos.bottom, right: pos.right, width: PANEL_W }}
                    className={`z-50 max-h-[70vh] overflow-y-auto rounded-2xl border border-ink-200 dark:border-ink-800 bg-white dark:bg-ink-900 shadow-overlay py-2 custom-scrollbar
                        transition duration-100 ease-out ${pos.flip ? 'origin-bottom-right' : 'origin-top-right'}
                        ${shown ? 'opacity-100 scale-100 translate-y-0' : `opacity-0 scale-95 ${pos.flip ? 'translate-y-1' : '-translate-y-1'}`}`}>
                    {/* Caret pointing back at the trigger (up when below it, down when flipped above) */}
                    <span aria-hidden="true" style={caretStyle}
                        className={`absolute size-2.5 rotate-45 bg-white dark:bg-ink-900 border-ink-200 dark:border-ink-800 ${pos.flip ? 'border-b border-r' : 'border-t border-l'}`} />
                    {visibleGroups.map((g, gi) => (
                        <div key={g.label} className={gi > 0 ? 'mt-1 pt-1 border-t border-ink-100 dark:border-ink-800' : ''}>
                            <p className="px-3 py-1 text-2xs font-semibold uppercase tracking-[0.14em] text-ink-400 dark:text-ink-500">{g.label}</p>
                            {g.items.map((it) => (
                                <button key={it.label} type="button" role="menuitem" disabled={it.disabled}
                                    onClick={() => { setOpen(false); it.onClick(); }}
                                    className="group w-full flex items-center gap-2.5 px-3 py-2 text-sm text-ink-700 dark:text-ink-200 hover:bg-brand-50 dark:hover:bg-brand-500/10 hover:text-brand-800 dark:hover:text-brand-200 disabled:opacity-40 disabled:cursor-not-allowed text-left transition-colors">
                                    {it.icon && <it.icon size={15} className="text-ink-400 group-hover:text-brand-500 shrink-0 transition-colors" />}
                                    {it.label}
                                </button>
                            ))}
                        </div>
                    ))}
                </div>,
                document.body,
            )}
        </>
    );
}
