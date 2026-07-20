import { useEffect, useRef, useState } from 'react';

/* ──────────────────────────────────────────────────────────────────────────
 * useDraftSafetyNet — protects free-text clinical notes from being lost to
 * an interruption (accidental navigation, browser crash, closed tab, shift
 * change) before the host form has an explicit save.
 *
 * This is a client-side (localStorage) layer only. Where a module already
 * has a server-side draft/resume concept (e.g. Clinical Desk's "Save draft"),
 * that remains the durable, cross-device source of truth — this hook only
 * covers the gap *before* the first explicit save, on this device.
 *
 * Storage-key isolation is the caller's responsibility and matters a lot
 * here: `storageKey` MUST encode the record the draft belongs to (e.g.
 * `clinicalDesk:${queue_id}`, `medicalHistoryEntry:${patient_id}:${entry_id
 * || 'new'}`) so one patient's draft can never surface on another patient's
 * form — this is PHI, not a generic form cache.
 *
 * Usage:
 *   const { hasSavedDraft, savedAt, applyDraft, discardDraft, clearDraft }
 *     = useDraftSafetyNet({ storageKey, value: formState, enabled: !!activePatient });
 *
 *   // hasSavedDraft → show a "Restore / Discard" banner
 *   // applyDraft()  → returns the stored value verbatim; caller applies it
 *   //                 to their own state (e.g. setFormState(applyDraft()))
 *   // discardDraft()→ clears the stored draft, keeps current state as-is
 *   // clearDraft()  → call after a successful submit so a stale draft can't
 *   //                 resurface on a later, unrelated encounter
 *
 * Nothing is ever applied automatically — restoring is always an explicit,
 * verbatim action the caller (and therefore the clinician) can see and
 * choose, never a silent overwrite or reformat of what was typed.
 * ────────────────────────────────────────────────────────────────────────── */

const PREFIX = 'hms:draft:';
const DEBOUNCE_MS = 1000;

function safeStringify(value) {
    try {
        return JSON.stringify(value);
    } catch {
        return null; // circular/unserializable — autosave just no-ops for this tick
    }
}

function readEntry(storageKey) {
    if (!storageKey) return null;
    try {
        const raw = localStorage.getItem(PREFIX + storageKey);
        if (!raw) return null;
        const parsed = JSON.parse(raw);
        if (!parsed || typeof parsed !== 'object' || !('value' in parsed)) return null;
        return parsed; // { value, savedAt }
    } catch {
        return null; // corrupt entry — never let a bad localStorage value break the form
    }
}

function writeEntry(storageKey, value) {
    try {
        localStorage.setItem(PREFIX + storageKey, JSON.stringify({ value, savedAt: Date.now() }));
    } catch {
        // Storage full / unavailable (private browsing, quota) — the safety
        // net silently no-ops rather than breaking the form in front of the
        // clinician. The server-side save path (where one exists) is
        // unaffected either way.
    }
}

function removeEntry(storageKey) {
    try {
        localStorage.removeItem(PREFIX + storageKey);
    } catch {
        // see writeEntry
    }
}

export default function useDraftSafetyNet({ storageKey, value, enabled = true }) {
    // Unacknowledged draft found for the current storageKey — null once the
    // caller has restored or discarded it (or there was never one).
    const [pending, setPending] = useState(null);
    // Autosave only runs once "armed" for the current key — either there was
    // nothing to protect on mount, or the caller resolved the banner.
    const armedRef = useRef(false);
    const timerRef = useRef(null);

    // (Re)initialise whenever we point at a different record.
    useEffect(() => {
        if (timerRef.current) clearTimeout(timerRef.current);
        if (!enabled || !storageKey) {
            armedRef.current = false;
            setPending(null);
            return;
        }
        const existing = readEntry(storageKey);
        if (existing) {
            armedRef.current = false;
            setPending(existing);
        } else {
            armedRef.current = true;
            setPending(null);
        }
        // Only re-run when we start looking at a genuinely different record.
    }, [storageKey, enabled]);

    // Debounced autosave — inert until armed, and keyed off the serialized
    // value so an object literal recreated every render doesn't restart the
    // debounce window unless its actual content changed.
    const serializedValue = safeStringify(value);
    useEffect(() => {
        if (!enabled || !storageKey || !armedRef.current || serializedValue === null) return undefined;
        if (timerRef.current) clearTimeout(timerRef.current);
        timerRef.current = setTimeout(() => {
            writeEntry(storageKey, value);
        }, DEBOUNCE_MS);
        return () => clearTimeout(timerRef.current);
        // `pending` is included so resolving the banner (which flips
        // armedRef without itself changing `value`) still kicks off a save.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [serializedValue, enabled, storageKey, pending]);

    const applyDraft = () => {
        const draftValue = pending?.value;
        armedRef.current = true;
        setPending(null);
        return draftValue;
    };

    const discardDraft = () => {
        removeEntry(storageKey);
        armedRef.current = true;
        setPending(null);
    };

    const clearDraft = () => {
        if (timerRef.current) clearTimeout(timerRef.current);
        removeEntry(storageKey);
    };

    return {
        hasSavedDraft: !!pending,
        savedAt: pending?.savedAt ? new Date(pending.savedAt) : null,
        applyDraft,
        discardDraft,
        clearDraft,
    };
}
