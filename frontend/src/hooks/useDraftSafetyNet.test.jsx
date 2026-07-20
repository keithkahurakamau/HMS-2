import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import useDraftSafetyNet from './useDraftSafetyNet';

// A tiny host component so we exercise the hook the way real callers do —
// through renders and explicit user actions — rather than calling it in
// isolation.
function Host({ storageKey, value, enabled = true }) {
    const { hasSavedDraft, savedAt, applyDraft, discardDraft, clearDraft } = useDraftSafetyNet({ storageKey, value, enabled });
    return (
        <div>
            <span data-testid="has-draft">{String(hasSavedDraft)}</span>
            <span data-testid="saved-at">{savedAt ? savedAt.getTime() : ''}</span>
            <button type="button" onClick={() => applyDraft()}>apply</button>
            <button type="button" onClick={discardDraft}>discard</button>
            <button type="button" onClick={clearDraft}>clear</button>
        </div>
    );
}

beforeEach(() => {
    localStorage.clear();
    vi.useFakeTimers();
});

afterEach(() => {
    vi.useRealTimers();
});

describe('useDraftSafetyNet', () => {
    it('debounce-saves the value to localStorage after the caller stops changing it', () => {
        const { rerender } = render(<Host storageKey="k1" value={{ text: 'a' }} />);
        expect(localStorage.getItem('hms:draft:k1')).toBeNull();

        rerender(<Host storageKey="k1" value={{ text: 'ab' }} />);
        act(() => { vi.advanceTimersByTime(999); });
        expect(localStorage.getItem('hms:draft:k1')).toBeNull(); // not yet — still inside the debounce window

        act(() => { vi.advanceTimersByTime(50); });
        const stored = JSON.parse(localStorage.getItem('hms:draft:k1'));
        expect(stored.value).toEqual({ text: 'ab' });
    });

    it('surfaces an existing draft as unacknowledged instead of overwriting it', () => {
        localStorage.setItem('hms:draft:k2', JSON.stringify({ value: { text: 'old draft' }, savedAt: Date.now() - 5000 }));
        render(<Host storageKey="k2" value={{ text: '' }} />);
        expect(screen.getByTestId('has-draft').textContent).toBe('true');

        // The blank freshly-mounted value must not clobber the stored draft
        // while it's unacknowledged.
        act(() => { vi.advanceTimersByTime(5000); });
        const stored = JSON.parse(localStorage.getItem('hms:draft:k2'));
        expect(stored.value).toEqual({ text: 'old draft' });
    });

    it('discardDraft clears storage and arms autosave for further edits', () => {
        localStorage.setItem('hms:draft:k3', JSON.stringify({ value: { text: 'old' }, savedAt: Date.now() }));
        const { rerender } = render(<Host storageKey="k3" value={{ text: 'old' }} />);
        expect(screen.getByTestId('has-draft').textContent).toBe('true');

        act(() => { screen.getByText('discard').click(); });
        expect(localStorage.getItem('hms:draft:k3')).toBeNull();
        expect(screen.getByTestId('has-draft').textContent).toBe('false');

        rerender(<Host storageKey="k3" value={{ text: 'fresh' }} />);
        act(() => { vi.advanceTimersByTime(1050); });
        const stored = JSON.parse(localStorage.getItem('hms:draft:k3'));
        expect(stored.value).toEqual({ text: 'fresh' });
    });

    it('clearDraft removes the entry after a successful save', () => {
        const { rerender } = render(<Host storageKey="k4" value={{ text: 'x' }} />);
        rerender(<Host storageKey="k4" value={{ text: 'xy' }} />);
        act(() => { vi.advanceTimersByTime(1050); });
        expect(localStorage.getItem('hms:draft:k4')).not.toBeNull();

        act(() => { screen.getByText('clear').click(); });
        expect(localStorage.getItem('hms:draft:k4')).toBeNull();
    });

    it('never lets one storageKey read or write another key\'s draft (PHI isolation)', () => {
        localStorage.setItem('hms:draft:patientA', JSON.stringify({ value: { text: 'A only' }, savedAt: Date.now() }));
        render(<Host storageKey="patientB" value={{ text: '' }} />);
        // A brand-new key with nothing saved for it must not surface patient A's draft.
        expect(screen.getByTestId('has-draft').textContent).toBe('false');
        expect(JSON.parse(localStorage.getItem('hms:draft:patientA')).value).toEqual({ text: 'A only' });
    });

    it('does nothing while disabled', () => {
        const { rerender } = render(<Host storageKey="k5" value={{ text: 'a' }} enabled={false} />);
        rerender(<Host storageKey="k5" value={{ text: 'ab' }} enabled={false} />);
        act(() => { vi.advanceTimersByTime(2000); });
        expect(localStorage.getItem('hms:draft:k5')).toBeNull();
    });
});
