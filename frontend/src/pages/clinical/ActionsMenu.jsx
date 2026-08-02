import React, { useState, useRef, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { ChevronDown } from 'lucide-react';

/**
 * Consolidated "Actions ▾" menu for the DoctorV2 clinical desk. Takes grouped
 * items; each item may carry a `perm` string — items the user lacks permission
 * for are hidden, and a group with no visible items disappears. The dropdown is
 * portaled to <body> and positioned under the trigger so it escapes the
 * workspace's overflow/stacking context.
 *
 * groups: [{ label, items: [{ label, icon, onClick, perm?, disabled? }] }]
 * has:    (perm) => boolean
 */
export default function ActionsMenu({ groups, has, disabled = false }) {
    const [open, setOpen] = useState(false);
    const [pos, setPos] = useState(null);
    const btnRef = useRef(null);
    const menuRef = useRef(null);

    // Single pass: drop items the user can't use, then drop empty groups.
    const visibleGroups = groups.reduce((acc, g) => {
        const items = g.items.filter((it) => !it.perm || has(it.perm));
        if (items.length) acc.push({ ...g, items });
        return acc;
    }, []);

    useEffect(() => {
        if (!open) return undefined;
        const place = () => {
            const r = btnRef.current?.getBoundingClientRect();
            if (r) setPos({ top: r.bottom + 6, right: window.innerWidth - r.right });
        };
        place();
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
            document.removeEventListener('mousedown', onDoc);
            document.removeEventListener('keydown', onKey);
            window.removeEventListener('resize', place);
            window.removeEventListener('scroll', place, true);
        };
    }, [open]);

    if (visibleGroups.length === 0) return null;

    return (
        <>
            <button ref={btnRef} type="button" disabled={disabled} onClick={() => setOpen((o) => !o)}
                aria-haspopup="menu" aria-expanded={open}
                className="btn-secondary text-sm gap-1.5">
                Actions <ChevronDown size={15} className={open ? 'rotate-180 transition-transform' : 'transition-transform'} />
            </button>
            {open && pos && createPortal(
                <div ref={menuRef} role="menu" style={{ position: 'fixed', top: pos.top, right: pos.right }}
                    className="z-50 w-60 max-h-[70vh] overflow-y-auto rounded-2xl border border-ink-200 dark:border-ink-800 bg-white dark:bg-ink-900 shadow-xl py-2 custom-scrollbar">
                    {visibleGroups.map((g, gi) => (
                        <div key={g.label} className={gi > 0 ? 'mt-1 pt-1 border-t border-ink-100 dark:border-ink-800' : ''}>
                            <p className="px-3 py-1 text-2xs font-semibold uppercase tracking-[0.14em] text-ink-400 dark:text-ink-500">{g.label}</p>
                            {g.items.map((it) => (
                                <button key={it.label} type="button" role="menuitem" disabled={it.disabled}
                                    onClick={() => { setOpen(false); it.onClick(); }}
                                    className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-ink-700 dark:text-ink-200 hover:bg-ink-50 dark:hover:bg-ink-800 disabled:opacity-40 disabled:cursor-not-allowed text-left">
                                    {it.icon && <it.icon size={15} className="text-ink-400 shrink-0" />}
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
