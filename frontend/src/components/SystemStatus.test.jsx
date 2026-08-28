import React from 'react';
import { render, screen, waitFor, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import SystemStatus from './SystemStatus';

const okResponse = () => Promise.resolve({ ok: true, json: () => Promise.resolve({ status: 'Operational' }) });

describe('SystemStatus', () => {
    beforeEach(() => {
        vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(true);
    });
    afterEach(() => {
        vi.restoreAllMocks();
    });

    it('reports the API as reachable once the probe succeeds', async () => {
        vi.stubGlobal('fetch', vi.fn(okResponse));
        render(<SystemStatus />);
        expect(await screen.findByText(/online/i)).toBeInTheDocument();
        expect(screen.getByRole('status')).toHaveAttribute('aria-live', 'polite');
    });

    it('probes the health endpoint, not a data route', async () => {
        const fetchMock = vi.fn(okResponse);
        vi.stubGlobal('fetch', fetchMock);
        render(<SystemStatus />);
        await waitFor(() => expect(fetchMock).toHaveBeenCalled());
        expect(fetchMock.mock.calls[0][0]).toContain('/api/health');
    });

    it('says the server is unreachable when the probe fails', async () => {
        vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('boom'))));
        render(<SystemStatus />);
        expect(await screen.findByText(/no server/i)).toBeInTheDocument();
    });

    it('says offline when the browser reports no network, without probing', async () => {
        navigator.onLine === true;
        vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false);
        const fetchMock = vi.fn(okResponse);
        vi.stubGlobal('fetch', fetchMock);
        render(<SystemStatus />);
        expect(await screen.findByText(/offline/i)).toBeInTheDocument();
        expect(fetchMock).not.toHaveBeenCalled();
    });

    it('never relies on colour alone: the state is always in the text', async () => {
        vi.stubGlobal('fetch', vi.fn(okResponse));
        render(<SystemStatus />);
        const pill = await screen.findByRole('status');
        expect(pill.textContent.trim().length).toBeGreaterThan(0);
    });

    it('re-probes when the browser fires an online event', async () => {
        const fetchMock = vi.fn(okResponse);
        vi.stubGlobal('fetch', fetchMock);
        render(<SystemStatus />);
        await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
        await act(async () => { window.dispatchEvent(new Event('online')); });
        await waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThan(1));
    });
});
