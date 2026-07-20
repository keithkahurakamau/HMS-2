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
 * Entries are encrypted (AES-GCM, Web Crypto API) before they ever touch
 * localStorage, with a random key generated once per browser profile and
 * kept alongside them. This does not defend against an attacker who can
 * already run script in this origin (XSS) — no client-only scheme can, since
 * the decryption key has to live somewhere script can reach it too, or the
 * safety net couldn't decrypt its own drafts after a reload. It does close
 * the more realistic risk for browser-local PHI caches: a shared clinic
 * workstation, someone glancing at devtools/localStorage, or raw disk/backup
 * forensics — never storing clinical text as plain, greppable text at rest,
 * consistent with this codebase's server-side PHI encryption work.
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
const KEY_STORAGE_KEY = 'hms:draft-key';
const DEBOUNCE_MS = 1000;

function safeStringify(value) {
    try {
        return JSON.stringify(value);
    } catch {
        return null; // circular/unserializable — autosave just no-ops for this tick
    }
}

function bytesToBase64(bytes) {
    let binary = '';
    bytes.forEach((b) => { binary += String.fromCharCode(b); });
    return btoa(binary);
}

function base64ToBytes(b64) {
    return Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
}

// Resolves to the same AES-GCM CryptoKey for the lifetime of this tab,
// generating (and persisting, base64-encoded) one on first use per browser
// profile. Memoized so repeated encrypt/decrypt calls share one lookup.
let cachedKeyPromise = null;
function getKey() {
    if (!cachedKeyPromise) {
        cachedKeyPromise = (async () => {
            const existing = localStorage.getItem(KEY_STORAGE_KEY);
            if (existing) {
                return crypto.subtle.importKey('raw', base64ToBytes(existing), 'AES-GCM', true, ['encrypt', 'decrypt']);
            }
            const key = await crypto.subtle.generateKey({ name: 'AES-GCM', length: 256 }, true, ['encrypt', 'decrypt']);
            const exported = await crypto.subtle.exportKey('raw', key);
            localStorage.setItem(KEY_STORAGE_KEY, bytesToBase64(new Uint8Array(exported)));
            return key;
        })();
    }
    return cachedKeyPromise;
}

async function encryptToBase64(plainText) {
    const key = await getKey();
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const ciphertext = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, new TextEncoder().encode(plainText));
    const combined = new Uint8Array(iv.length + ciphertext.byteLength);
    combined.set(iv, 0);
    combined.set(new Uint8Array(ciphertext), iv.length);
    return bytesToBase64(combined);
}

async function decryptFromBase64(b64) {
    const key = await getKey();
    const combined = base64ToBytes(b64);
    const iv = combined.slice(0, 12);
    const ciphertext = combined.slice(12);
    const plainBuf = await crypto.subtle.decrypt({ name: 'AES-GCM', iv }, key, ciphertext);
    return new TextDecoder().decode(plainBuf);
}

async function readEntry(storageKey) {
    if (!storageKey) return null;
    try {
        const raw = localStorage.getItem(PREFIX + storageKey);
        if (!raw) return null;
        const parsed = JSON.parse(await decryptFromBase64(raw));
        if (!parsed || typeof parsed !== 'object' || !('value' in parsed)) return null;
        return parsed; // { value, savedAt }
    } catch {
        return null; // corrupt/undecryptable entry — never let a bad value break the form
    }
}

async function writeEntry(storageKey, value) {
    try {
        const plainText = JSON.stringify({ value, savedAt: Date.now() });
        localStorage.setItem(PREFIX + storageKey, await encryptToBase64(plainText));
    } catch {
        // Storage full/unavailable (private browsing, quota), or Web Crypto
        // unsupported in this context — the safety net silently no-ops
        // rather than breaking the form in front of the clinician. The
        // server-side save path (where one exists) is unaffected either way.
    }
}

function removeEntry(storageKey) {
    try {
        localStorage.removeItem(PREFIX + storageKey);
    } catch {
        // see writeEntry
    }
}

// `pending` has three states, not two — this distinction is what keeps
// autosave from ever racing the (necessarily async, decrypting) lookup and
// clobbering an unacknowledged draft before it's had a chance to load:
//   undefined → haven't checked storage for this identity yet
//   null      → checked; nothing there (autosave armed)
//   object    → checked; found an unacknowledged draft (autosave inert)
export default function useDraftSafetyNet({ storageKey, value, enabled = true }) {
    const identity = enabled ? storageKey : null;

    const [pending, setPending] = useState(undefined);
    // Tracks which identity `pending` currently reflects.
    const [initializedFor, setInitializedFor] = useState(undefined);
    const timerRef = useRef(null);

    // The instant we start pointing at a different record, drop back to
    // "haven't checked yet" synchronously — during render, not in an effect
    // (React's documented alternative to an effect for "adjust state when a
    // prop changes"). This guarantees the recovery banner can never show a
    // frame of the *previous* record's draft; the real answer for the new
    // record arrives a moment later via the lookup effect below. Only state
    // is touched here (never a ref) — render must stay pure.
    if (identity !== initializedFor) {
        setInitializedFor(identity);
        setPending(undefined);
    }

    // Look up (and decrypt) any existing draft for this identity.
    useEffect(() => {
        if (!identity) {
            setPending(null);
            return undefined;
        }
        let cancelled = false;
        readEntry(identity).then((existing) => {
            if (!cancelled) setPending(existing ?? null);
        });
        return () => { cancelled = true; };
    }, [identity]);

    // Debounced, encrypted autosave — inert until the lookup above has
    // resolved for this identity (pending !== undefined) and found nothing
    // unacknowledged (pending === null). Keyed off the serialized value so
    // an object literal recreated every render doesn't restart the debounce
    // window unless its actual content changed. The effect's own cleanup
    // clears any in-flight timer whenever identity/value/pending change —
    // including a record switch — so a stale write can never land under the
    // wrong key.
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
