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
    const identity = enabled ? storageKey : null;

    // Unacknowledged draft found for the current identity — null once the
    // caller has restored/discarded it, or there was never one. Autosave is
    // "armed" exactly when this is null, so no separate flag is needed.
    const [pending, setPending] = useState(null);
    // Tracks which identity `pending` currently reflects.
    const [initializedFor, setInitializedFor] = useState(undefined);
    const timerRef = useRef(null);

    // Adjust `pending` synchronously when we start pointing at a different
    // record — React's documented alternative to an effect for "adjust
    // state when a prop changes" (react.dev/learn/you-might-not-need-an-effect).
    // Done during render, not in a useEffect, so there is never a frame
    // where the recovery banner still reflects the previous record's draft
    // before an effect catches up — this is PHI, so that flash matters.
    // Only state is touched here (never a ref) — render must stay pure.
    if (identity !== initializedFor) {
        setInitializedFor(identity);
        setPending(identity ? readEntry(identity) : null);
    }

    // Debounced autosave — inert while a draft is still unacknowledged
    // (pending !== null), and keyed off the serialized value so an object
    // literal recreated every render doesn't restart the debounce window
    // unless its actual content changed. The effect's own cleanup clears
    // any in-flight timer whenever identity/value/pending change — including
    // a record switch — so a stale write can never land under the wrong key.
    const serializedValue = safeStringify(value);
    useEffect(() => {
        if (!identity || pending !== null || serializedValue === null) return undefined;
        timerRef.current = setTimeout(() => {
            writeEntry(identity, value);
        }, DEBOUNCE_MS);
        return () => clearTimeout(timerRef.current);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [serializedValue, identity, pending]);

    const applyDraft = () => {
        const draftValue = pending?.value;
        setPending(null);
        return draftValue;
    };

    const discardDraft = () => {
        removeEntry(identity);
        setPending(null);
    };

    const clearDraft = () => {
        clearTimeout(timerRef.current);
        removeEntry(identity);
    };

    return {
        hasSavedDraft: !!pending,
        savedAt: pending?.savedAt ? new Date(pending.savedAt) : null,
        applyDraft,
        discardDraft,
        clearDraft,
    };
}
