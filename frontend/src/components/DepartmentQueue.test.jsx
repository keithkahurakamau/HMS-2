import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../test/renderWithProviders';

vi.mock('../api/client', () => ({
    apiClient: { get: vi.fn(), patch: vi.fn(), post: vi.fn() },
    isTenantRedirect: vi.fn(() => false),
}));
vi.mock('react-hot-toast', () => {
    const toast = vi.fn(); toast.success = vi.fn(); toast.error = vi.fn();
    return { default: toast };
});

import { apiClient } from '../api/client';
import DepartmentQueue from './DepartmentQueue';

describe('DepartmentQueue', () => {
    beforeEach(() => vi.clearAllMocks());

    it('lists patients routed to the department', async () => {
        apiClient.get.mockResolvedValueOnce({ data: [
            { queue_id: 11, patient_id: 5, patient_name: 'Jane Doe', department: 'Pharmacy', acuity_level: 3, status: 'Waiting', joined_at: '2026-06-24T08:00:00Z' },
        ]});
        renderWithProviders(<DepartmentQueue department="Pharmacy" />);
        await waitFor(() => expect(apiClient.get).toHaveBeenCalledWith('/queue/?department=Pharmacy'));
        expect(await screen.findByText('Jane Doe')).toBeInTheDocument();
    });

    it('falls back to Patient #<id> when patient_name is absent', async () => {
        apiClient.get.mockResolvedValueOnce({ data: [
            { queue_id: 11, patient_id: 5, department: 'Pharmacy', acuity_level: 3, status: 'Waiting', joined_at: '2026-06-24T08:00:00Z' },
        ]});
        renderWithProviders(<DepartmentQueue department="Pharmacy" />);
        expect(await screen.findByText('Patient #5')).toBeInTheDocument();
    });

    it('removes a patient via checkout', async () => {
        apiClient.get.mockResolvedValue({ data: [
            { queue_id: 12, patient_id: 6, patient_name: 'John Smith', department: 'Pharmacy', acuity_level: 3, status: 'Waiting', joined_at: '2026-06-24T08:00:00Z' },
        ]});
        apiClient.patch.mockResolvedValueOnce({ data: { queue_id: 12, status: 'Completed' } });
        renderWithProviders(<DepartmentQueue department="Pharmacy" />);
        const removeBtn = await screen.findByRole('button', { name: /remove/i });
        await userEvent.click(removeBtn);
        await waitFor(() => expect(apiClient.patch).toHaveBeenCalledWith('/queue/12/checkout'));
    });

    it('cancels a patient after prompting for a reason', async () => {
        vi.spyOn(window, 'prompt').mockReturnValue('left');
        apiClient.get.mockResolvedValue({ data: [
            { queue_id: 13, patient_id: 7, patient_name: 'Alice Njeri', department: 'Pharmacy', acuity_level: 2, status: 'Waiting', joined_at: '2026-06-24T09:00:00Z' },
        ]});
        apiClient.patch.mockResolvedValueOnce({ data: { queue_id: 13, status: 'Cancelled' } });
        renderWithProviders(<DepartmentQueue department="Pharmacy" />);
        const cancelBtn = await screen.findByRole('button', { name: /cancel/i });
        await userEvent.click(cancelBtn);
        await waitFor(() =>
            expect(apiClient.patch).toHaveBeenCalledWith('/queue/13/cancel', { reason: 'left' }),
        );
        vi.restoreAllMocks();
    });

    it('renders a custom title when provided', async () => {
        apiClient.get.mockResolvedValueOnce({ data: [] });
        renderWithProviders(<DepartmentQueue department="Lab" title="Lab patients" />);
        expect(await screen.findByText('Lab patients')).toBeInTheDocument();
    });

    it('shows empty state when no rows are returned', async () => {
        apiClient.get.mockResolvedValueOnce({ data: [] });
        renderWithProviders(<DepartmentQueue department="Radiology" />);
        expect(await screen.findByText(/no patients routed here/i)).toBeInTheDocument();
    });

    it('inline mode renders nothing when there are no routed patients', async () => {
        apiClient.get.mockResolvedValueOnce({ data: [] });
        const { container } = renderWithProviders(<DepartmentQueue department="Pharmacy" inline />);
        await waitFor(() => expect(apiClient.get).toHaveBeenCalled());
        // No empty-state box, no "routed from triage" header — just nothing.
        expect(screen.queryByText(/no patients routed here/i)).not.toBeInTheDocument();
        expect(screen.queryByText(/routed from triage/i)).not.toBeInTheDocument();
        expect(container).toBeEmptyDOMElement();
    });

    it('inline mode tags each routed patient and shows the strip header', async () => {
        apiClient.get.mockResolvedValueOnce({ data: [
            { queue_id: 21, patient_id: 9, patient_name: 'Sam Otieno', department: 'Pharmacy', acuity_level: 2, status: 'Waiting', joined_at: '2026-06-25T08:00:00Z' },
        ]});
        renderWithProviders(<DepartmentQueue department="Pharmacy" inline />);
        expect(await screen.findByText('Sam Otieno')).toBeInTheDocument();
        expect(screen.getByText(/routed from triage/i)).toBeInTheDocument();
        expect(screen.getByText('Routed')).toBeInTheDocument();
    });
});
