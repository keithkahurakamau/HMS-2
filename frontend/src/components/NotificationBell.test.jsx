import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Toaster } from 'react-hot-toast';
import { renderWithProviders } from '../test/renderWithProviders';

// toast.custom() only renders through a mounted <Toaster /> — render it
// alongside the bell so the sneak-peek toast actually appears in the DOM
// (a higher-fidelity check than mocking toast.custom's internals).
const renderBell = () => renderWithProviders(<><NotificationBell /><Toaster /></>);

vi.mock('../api/client', () => ({
    apiClient: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
    isTenantRedirect: vi.fn(() => false),
}));
vi.mock('../context/AuthContext', async (orig) => {
    const actual = await orig();
    return { ...actual, useAuth: () => ({ user: { user_id: 42, role: 'Doctor' } }) };
});

// The live socket is exercised by useNotificationSocket's own unit tests
// (mirrors the already-shipped usePaymentSocket pattern) and would otherwise
// try to open a real WebSocket in jsdom — capture the onEvent callback
// instead so tests can simulate a push without a real connection.
let capturedOnEvent = null;
vi.mock('../hooks/useNotificationSocket', () => ({
    default: (enabled, userId, role, onEvent) => { capturedOnEvent = onEvent; },
}));

import { apiClient } from '../api/client';
import NotificationBell from './NotificationBell';

const EXISTING = [
    { notification_id: 1, category: 'info', title: 'Welcome', body: 'Existing item', is_read: true, created_at: '2026-07-01T09:00:00Z' },
];

beforeEach(() => {
    vi.clearAllMocks();
    capturedOnEvent = null;
});

describe('NotificationBell', () => {
    it('renders the unread badge from the initial fetch', async () => {
        apiClient.get.mockResolvedValue({ data: { notifications: EXISTING, unread_count: 0 } });
        renderBell();
        await waitFor(() => expect(apiClient.get).toHaveBeenCalledWith('/notifications/'));
        expect(screen.queryByText('0')).not.toBeInTheDocument(); // no badge when unread_count is 0
    });

    it('a live push adds the notification to the bell immediately, without waiting for a poll', async () => {
        apiClient.get.mockResolvedValue({ data: { notifications: EXISTING, unread_count: 0 } });
        const user = userEvent.setup();
        renderBell();
        await waitFor(() => expect(capturedOnEvent).toBeInstanceOf(Function));

        capturedOnEvent({
            type: 'notification', notification_id: 99, category: 'critical',
            title: 'Critical lab result', body: 'Potassium 6.8 — flagged critical',
            link: '/app/laboratory?test_id=99', created_at: '2026-07-20T12:00:00Z',
        });

        // Bell badge updates immediately.
        expect(await screen.findByLabelText(/notifications, 1 unread/i)).toBeInTheDocument();

        // ...and the item is already in the dropdown (no extra fetch needed).
        // The sneak-peek toast is still up too, so scope to the inbox panel
        // specifically rather than asserting on the page as a whole.
        await user.click(screen.getByLabelText(/notifications, 1 unread/i));
        const inbox = screen.getByRole('dialog', { name: /notification inbox/i });
        expect(within(inbox).getByText('Critical lab result')).toBeInTheDocument();
    });

    it('a live push shows a sneak-peek toast that navigates and marks read on click', async () => {
        apiClient.get.mockResolvedValue({ data: { notifications: [], unread_count: 0 } });
        apiClient.patch.mockResolvedValue({ data: {} });
        const user = userEvent.setup();
        renderBell();
        await waitFor(() => expect(capturedOnEvent).toBeInstanceOf(Function));

        capturedOnEvent({
            type: 'notification', notification_id: 7, category: 'warning',
            title: 'Prescription returned', body: 'Pharmacy sent this back for review',
            link: '/app/clinical', created_at: '2026-07-20T12:00:00Z',
        });

        const toastCard = await screen.findByText('Prescription returned');
        await user.click(toastCard);
        await waitFor(() => expect(apiClient.patch).toHaveBeenCalledWith('/notifications/7/read'));
    });

    it('ignores a duplicate push for a notification it already has', async () => {
        apiClient.get.mockResolvedValue({ data: { notifications: EXISTING, unread_count: 0 } });
        renderBell();
        await waitFor(() => expect(capturedOnEvent).toBeInstanceOf(Function));

        capturedOnEvent({
            type: 'notification', notification_id: 1, category: 'info',
            title: 'Welcome', body: 'Existing item', link: null, created_at: '2026-07-01T09:00:00Z',
        });

        // Still just the one badge-worth of unread, not double-counted.
        expect(await screen.findByLabelText(/notifications, 1 unread/i)).toBeInTheDocument();
    });
});
