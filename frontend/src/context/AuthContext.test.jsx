import React from 'react';
import { render, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('../api/client', () => ({ apiClient: { get: vi.fn() } }));
import { apiClient } from '../api/client';
import { AuthProvider } from './AuthContext';

const atPath = (path) => {
    window.history.pushState({}, '', path);
};

describe('AuthProvider bootstrap', () => {
    beforeEach(() => {
        apiClient.get.mockReset();
        apiClient.get.mockResolvedValue({ data: {} });
    });
    afterEach(() => atPath('/'));

    it('checks the tenant session on a workspace route', async () => {
        atPath('/app/home');
        render(<AuthProvider><div /></AuthProvider>);
        await waitFor(() => expect(apiClient.get).toHaveBeenCalledWith('/users/me'));
    });

    it('does not call the tenant session endpoint on the superadmin console', async () => {
        // The console authenticates with a platform token of its own. Calling
        // /users/me there has no tenant header, so it 400s on every page load.
        atPath('/superadmin/dashboard');
        render(<AuthProvider><div /></AuthProvider>);
        await waitFor(() => expect(apiClient.get).not.toHaveBeenCalled());
    });

    it('does not call it on the superadmin login page either', async () => {
        atPath('/superadmin/login');
        render(<AuthProvider><div /></AuthProvider>);
        await waitFor(() => expect(apiClient.get).not.toHaveBeenCalled());
    });
});
