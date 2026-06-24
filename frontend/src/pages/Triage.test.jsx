import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../test/renderWithProviders';

vi.mock('../api/client', () => ({
    apiClient: { get: vi.fn(), post: vi.fn() },
    isTenantRedirect: vi.fn(() => false),
}));
vi.mock('react-hot-toast', () => {
    const toast = vi.fn(); toast.success = vi.fn(); toast.error = vi.fn();
    return { default: toast };
});

import { apiClient } from '../api/client';
import Triage from './Triage';

describe('Triage disposition', () => {
    beforeEach(() => vi.clearAllMocks());

    it('submits the chosen disposition (not hardcoded Consultation)', async () => {
        apiClient.get.mockResolvedValueOnce({ data: [
            { queue_id: 1, patient_id: 2, outpatient_no: 'OPD1', patient_name: 'Jane Doe', age: 30, gender: 'F', joined_time: '08:00 AM', status: 'Waiting', allergies: 'None' },
        ]});
        apiClient.post.mockResolvedValue({ data: { message: 'ok', disposition: 'Laboratory' } });

        renderWithProviders(<Triage />);
        await userEvent.click(await screen.findByText('Jane Doe'));
        // record a vital so submit is allowed
        await userEvent.type(screen.getByLabelText(/RBS/i), '5.5');
        // choose Laboratory in the disposition selector
        await userEvent.selectOptions(screen.getByLabelText(/route to|disposition|send to/i), 'Laboratory');
        await userEvent.click(screen.getByRole('button', { name: /save/i }));

        await waitFor(() => expect(apiClient.post).toHaveBeenCalled());
        const body = apiClient.post.mock.calls[0][1];
        expect(body.disposition).toBe('Laboratory');
    });
});
