import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../test/renderWithProviders';

const restartAll = vi.fn();
vi.mock('../context/JourneyContext', () => ({
    useJourney: () => ({ restartAll }),
}));
vi.mock('../context/AuthContext', async (orig) => {
    const actual = await orig();
    return { ...actual, useAuth: () => ({ user: { user_id: 42 } }) };
});

import { APP_VERSION } from '../releases';
import WhatsNew from './WhatsNew';

describe('WhatsNew', () => {
    beforeEach(() => { localStorage.clear(); vi.clearAllMocks(); });

    it('shows the announcement when the user has not seen the current version', async () => {
        renderWithProviders(<WhatsNew />);
        expect(await screen.findByText(/what's new/i)).toBeInTheDocument();
        expect(screen.getByText(/Clinical flow improvements/i)).toBeInTheDocument();
    });

    it('hides and persists last-seen after dismiss', async () => {
        renderWithProviders(<WhatsNew />);
        // findAllByRole because both the X ("Close") and "Got it" buttons match the regex;
        // click the last one (Got it) which is the primary dismiss action.
        const btns = await screen.findAllByRole('button', { name: /got it|dismiss|close/i });
        await userEvent.click(btns[btns.length - 1]);
        await waitFor(() => expect(localStorage.getItem('hms_last_seen_version_42')).toBe(APP_VERSION));
    });

    it('does not show when already on current version', async () => {
        localStorage.setItem('hms_last_seen_version_42', APP_VERSION);
        renderWithProviders(<WhatsNew />);
        await waitFor(() => expect(screen.queryByText(/what's new/i)).not.toBeInTheDocument());
    });
});
