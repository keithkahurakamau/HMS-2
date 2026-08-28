import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('../api/client', () => ({ apiClient: { get: vi.fn() } }));
import { apiClient } from '../api/client';
import PlatformHealth from './PlatformHealth';

const healthy = {
    '/public/superadmin/payhero/webhook-health': { ready: true, blockers: [], environment: 'development' },
    '/public/superadmin/platform-payhero/health': { config: { configured: true } },
};

const route = (map) => (url) =>
    url in map ? Promise.resolve({ data: map[url] }) : Promise.reject(new Error(`unmocked ${url}`));

describe('PlatformHealth', () => {
    beforeEach(() => {
        vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: true })));
        vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(true);
    });
    afterEach(() => vi.restoreAllMocks());

    it('reports all clear when every check passes', async () => {
        apiClient.get.mockImplementation(route(healthy));
        render(<PlatformHealth />);
        expect(await screen.findByText(/all clear/i)).toBeInTheDocument();
    });

    it('counts and names what is wrong', async () => {
        apiClient.get.mockImplementation(route({
            ...healthy,
            '/public/superadmin/payhero/webhook-health': {
                ready: false,
                environment: 'production',
                blockers: [
                    'PUBLIC_BASE_URL is not set.',
                    'PAYHERO_WEBHOOK_SECRET is empty.',
                ],
            },
        }));
        render(<PlatformHealth />);
        expect(await screen.findByText(/2 issues/i)).toBeInTheDocument();

        await userEvent.click(screen.getByRole('button', { name: /2 issues/i }));
        expect(screen.getByText(/PUBLIC_BASE_URL is not set\./)).toBeInTheDocument();
        expect(screen.getByText(/PAYHERO_WEBHOOK_SECRET is empty\./)).toBeInTheDocument();
    });

    it('flags subscription billing when it is not configured', async () => {
        apiClient.get.mockImplementation(route({
            ...healthy,
            '/public/superadmin/platform-payhero/health': { config: { configured: false } },
        }));
        render(<PlatformHealth />);
        expect(await screen.findByText(/1 issue/i)).toBeInTheDocument();
    });

    it('surfaces a failed check itself as an issue rather than crashing', async () => {
        apiClient.get.mockImplementation(() => Promise.reject(new Error('403')));
        render(<PlatformHealth />);
        await waitFor(() => expect(screen.getByRole('button')).toBeInTheDocument());
        expect(screen.getByRole('button').textContent).toMatch(/issue/i);
    });

    it('announces itself politely for screen readers', async () => {
        apiClient.get.mockImplementation(route(healthy));
        render(<PlatformHealth />);
        await screen.findByText(/all clear/i);
        expect(screen.getByRole('status')).toHaveAttribute('aria-live', 'polite');
    });
});
