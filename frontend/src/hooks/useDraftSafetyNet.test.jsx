import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import useDraftSafetyNet from './useDraftSafetyNet';

// A tiny host component so we exercise the hook the way real callers do —
// through mounts/rerenders/clicks — rather than calling it in isolation.
// Entries are encrypted at rest, so tests verify behavior entirely through
// this public interface (mount a fresh Host for the same key and see what
// it finds) rather than by inspecting raw localStorage content.
function Host({ storageKey, value, enabled = true, onApplied }) {
    const { hasSavedDraft, applyDraft, discardDraft, clearDraft } = useDraftSafetyNet({ storageKey, value, enabled });
    return (
        <div>
            <span data-testid="has-draft">{String(hasSavedDraft)}</span>
            <button type="button" onClick={() => onApplied?.(applyDraft())}>apply</button>
            <button type="button" onClick={discardDraft}>discard</button>
            <button type="button" onClick={clearDraft}>clear</button>
        </div>
    );
}

// Real timers throughout — encryption is real async Web Crypto work, so
// mixing it with fake timers just to speed up the ~1s debounce isn't worth
// the added fragility. Generous waitFor timeouts absorb the real delay.
const DEBOUNCE_WAIT = { timeout: 3000 };
const settle = (ms) => new Promise((resolve) => { setTimeout(resolve, ms); });

beforeEach(() => {
    localStorage.clear();
});

describe('useDraftSafetyNet', () => {
    it('debounce-saves the value, and a later mount for the same key restores it verbatim', async () => {
        const { rerender, unmount } = render(<Host storageKey="k1" value={{ text: 'a' }} />);
        rerender(<Host storageKey="k1" value={{ text: 'ab' }} />);
        await settle(1200); // past the debounce window, long enough for the encrypt round trip
        unmount();

        const applied = vi.fn();
        render(<Host storageKey="k1" value={{ text: '' }} onApplied={applied} />);
        await waitFor(() => expect(screen.getByTestId('has-draft').textContent).toBe('true'), DEBOUNCE_WAIT);
        fireEvent.click(screen.getByText('apply'));
        expect(applied).toHaveBeenCalledWith({ text: 'ab' });
    });

    it('surfaces an existing draft as unacknowledged and never lets autosave overwrite it while unresolved', async () => {
        const { unmount: unmountA } = render(<Host storageKey="k2" value={{ text: 'old draft' }} />);
        await settle(1200);
        unmountA();

        // A fresh mount with different (blank) current-form content must not
        // clobber the stored draft just because the debounce window elapses
        // — it's still unacknowledged.
        const { unmount: unmountB } = render(<Host storageKey="k2" value={{ text: '' }} />);
        await waitFor(() => expect(screen.getByTestId('has-draft').textContent).toBe('true'), DEBOUNCE_WAIT);
        await settle(1200);
        unmountB();

        const applied = vi.fn();
        render(<Host storageKey="k2" value={{ text: '' }} onApplied={applied} />);
        await waitFor(() => expect(screen.getByTestId('has-draft').textContent).toBe('true'), DEBOUNCE_WAIT);
        fireEvent.click(screen.getByText('apply'));
        expect(applied).toHaveBeenCalledWith({ text: 'old draft' });
    });

    it('discardDraft clears the old entry and arms autosave for further edits', async () => {
        const { unmount: unmountA } = render(<Host storageKey="k3" value={{ text: 'old' }} />);
        await settle(1200);
        unmountA();

        const { rerender, unmount: unmountB } = render(<Host storageKey="k3" value={{ text: 'old' }} />);
        await waitFor(() => expect(screen.getByTestId('has-draft').textContent).toBe('true'), DEBOUNCE_WAIT);
        fireEvent.click(screen.getByText('discard'));
        expect(screen.getByTestId('has-draft').textContent).toBe('false');

        rerender(<Host storageKey="k3" value={{ text: 'fresh' }} />);
        await settle(1200);
        unmountB();

        const applied = vi.fn();
        render(<Host storageKey="k3" value={{ text: 'fresh' }} onApplied={applied} />);
        await waitFor(() => expect(screen.getByTestId('has-draft').textContent).toBe('true'), DEBOUNCE_WAIT);
        fireEvent.click(screen.getByText('apply'));
        expect(applied).toHaveBeenCalledWith({ text: 'fresh' });
    });

    it('clearDraft removes the entry after a successful save', async () => {
        const { rerender, unmount } = render(<Host storageKey="k4" value={{ text: 'x' }} />);
        rerender(<Host storageKey="k4" value={{ text: 'xy' }} />);
        await settle(1200);
        fireEvent.click(screen.getByText('clear'));
        unmount();

        render(<Host storageKey="k4" value={{ text: '' }} />);
        await settle(1200);
        expect(screen.getByTestId('has-draft').textContent).toBe('false');
    });

    it('never lets one storageKey read or write another key\'s draft (PHI isolation)', async () => {
        const { unmount: unmountA } = render(<Host storageKey="patientA" value={{ text: 'A only' }} />);
        await settle(1200);
        unmountA();

        // A different patient's key must not see patient A's draft.
        const { unmount: unmountB } = render(<Host storageKey="patientB" value={{ text: '' }} />);
        await settle(1200);
        expect(screen.getByTestId('has-draft').textContent).toBe('false');
        unmountB();

        // Patient A's own draft must still be there, untouched by B mounting.
        const applied = vi.fn();
        render(<Host storageKey="patientA" value={{ text: '' }} onApplied={applied} />);
        await waitFor(() => expect(screen.getByTestId('has-draft').textContent).toBe('true'), DEBOUNCE_WAIT);
        fireEvent.click(screen.getByText('apply'));
        expect(applied).toHaveBeenCalledWith({ text: 'A only' });
    });

    it('does nothing while disabled', async () => {
        const { rerender, unmount } = render(<Host storageKey="k5" value={{ text: 'a' }} enabled={false} />);
        rerender(<Host storageKey="k5" value={{ text: 'ab' }} enabled={false} />);
        await settle(1200);
        unmount();

        render(<Host storageKey="k5" value={{ text: '' }} enabled />);
        await settle(1200);
        expect(screen.getByTestId('has-draft').textContent).toBe('false');
    });
});
