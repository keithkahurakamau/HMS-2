import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/renderWithProviders';

vi.mock('../../api/client', () => ({
    apiClient: {
        get: vi.fn(),
        post: vi.fn(),
    },
}));

vi.mock('react-hot-toast', () => ({
    default: Object.assign(vi.fn(), {
        success: vi.fn(),
        error: vi.fn(),
    }),
}));

import { apiClient } from '../../api/client';
import toast from 'react-hot-toast';
import StarterCatalogueTab from './StarterCatalogueTab';

beforeEach(() => {
    vi.clearAllMocks();
});

describe('StarterCatalogueTab', () => {
    it('shows a clean "not loaded yet" state when the catalogue is unavailable', async () => {
        apiClient.get.mockResolvedValue({ data: { available: false, products: [] } });
        renderWithProviders(<StarterCatalogueTab canManage={true} />);

        expect(await screen.findByText(/starter catalogue not loaded yet/i)).toBeInTheDocument();
        expect(screen.queryByText(/adopt all/i)).not.toBeInTheDocument();
    });

    it('shows the same clean state when the request itself fails, never crashing', async () => {
        apiClient.get.mockRejectedValue(new Error('network down'));
        renderWithProviders(<StarterCatalogueTab canManage={true} />);

        expect(await screen.findByText(/starter catalogue not loaded yet/i)).toBeInTheDocument();
    });

    it('lists products and lets a manager adopt everything', async () => {
        apiClient.get.mockResolvedValue({
            data: { available: true, products: ['Paracetamol 500mg', 'Amoxicillin 250mg'] },
        });
        apiClient.post.mockResolvedValue({ data: { created: 2, skipped: 0, created_items: [], skipped_items: [] } });

        renderWithProviders(<StarterCatalogueTab canManage={true} />);

        expect(await screen.findByText('Paracetamol 500mg')).toBeInTheDocument();
        expect(screen.getByText('Amoxicillin 250mg')).toBeInTheDocument();

        const user = userEvent.setup();
        await user.click(screen.getByRole('button', { name: /adopt all/i }));

        await waitFor(() => {
            expect(apiClient.post).toHaveBeenCalledWith(
                '/pharmacy/starter-catalogue/adopt',
                { names: undefined }
            );
        });
        expect(toast.success).toHaveBeenCalledWith(expect.stringContaining('Added 2'));
    });

    it('adopts only the checked subset via "Adopt selected"', async () => {
        apiClient.get.mockResolvedValue({
            data: { available: true, products: ['Paracetamol 500mg', 'Amoxicillin 250mg'] },
        });
        apiClient.post.mockResolvedValue({ data: { created: 1, skipped: 0, created_items: [], skipped_items: [] } });

        renderWithProviders(<StarterCatalogueTab canManage={true} />);
        await screen.findByText('Paracetamol 500mg');

        const user = userEvent.setup();
        await user.click(screen.getByRole('checkbox', { name: 'Paracetamol 500mg' }));
        await user.click(screen.getByRole('button', { name: /adopt selected/i }));

        await waitFor(() => {
            expect(apiClient.post).toHaveBeenCalledWith(
                '/pharmacy/starter-catalogue/adopt',
                { names: ['Paracetamol 500mg'] }
            );
        });
    });

    it('reports items already in inventory as skipped, without erroring', async () => {
        apiClient.get.mockResolvedValue({
            data: { available: true, products: ['Paracetamol 500mg'] },
        });
        apiClient.post.mockResolvedValue({
            data: { created: 0, skipped: 1, created_items: [], skipped_items: ['Paracetamol 500mg'] },
        });

        renderWithProviders(<StarterCatalogueTab canManage={true} />);
        await screen.findByText('Paracetamol 500mg');

        const user = userEvent.setup();
        await user.click(screen.getByRole('button', { name: /adopt all/i }));

        await waitFor(() => {
            expect(toast).toHaveBeenCalledWith(expect.stringContaining('Already in your inventory'));
        });
    });

    it('hides the adopt controls for a user without pharmacy:manage', async () => {
        apiClient.get.mockResolvedValue({
            data: { available: true, products: ['Paracetamol 500mg'] },
        });
        renderWithProviders(<StarterCatalogueTab canManage={false} />);

        await screen.findByText('Paracetamol 500mg');
        expect(screen.queryByRole('button', { name: /adopt all/i })).not.toBeInTheDocument();
        expect(screen.queryByRole('button', { name: /adopt selected/i })).not.toBeInTheDocument();
    });
});
