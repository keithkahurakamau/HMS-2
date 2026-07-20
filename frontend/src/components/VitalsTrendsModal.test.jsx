import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../api/client', () => ({
    apiClient: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
    isTenantRedirect: vi.fn(() => false),
}));

import { apiClient } from '../api/client';
import VitalsTrendsModal from './VitalsTrendsModal';

const PATIENT = { patient_id: 7, patient_name: 'Jane Doe', outpatient_no: 'OP-0007' };
const HISTORY = [
    {
        record_id: 1, recorded_at: '2026-07-01T09:00:00Z', blood_pressure: '118/76',
        heart_rate: 70, respiratory_rate: 15, temperature: 36.8, spo2: 99,
        weight_kg: 64, height_cm: 165, bmi: 23.5,
    },
    {
        record_id: 2, recorded_at: '2026-07-10T09:00:00Z', blood_pressure: '124/82',
        heart_rate: 78, respiratory_rate: 17, temperature: 37.1, spo2: 97,
        weight_kg: 65, height_cm: 165, bmi: 23.9,
    },
];

beforeEach(() => {
    vi.clearAllMocks();
});

describe('VitalsTrendsModal', () => {
    it('fetches the vitals history and renders one row per reading', async () => {
        apiClient.get.mockResolvedValue({ data: HISTORY });
        render(<VitalsTrendsModal patient={PATIENT} onClose={() => {}} />);
        expect(await screen.findByText('118/76')).toBeInTheDocument();
        expect(screen.getByText('124/82')).toBeInTheDocument();
        expect(apiClient.get).toHaveBeenCalledWith('/clinical/patients/7/vitals-history');
    });

    it('shows an empty state when there are no past readings', async () => {
        apiClient.get.mockResolvedValue({ data: [] });
        render(<VitalsTrendsModal patient={PATIENT} onClose={() => {}} />);
        expect(await screen.findByText(/no past vitals/i)).toBeInTheDocument();
    });

    it('calls onClose from the close button', async () => {
        const user = userEvent.setup();
        const onClose = vi.fn();
        apiClient.get.mockResolvedValue({ data: HISTORY });
        render(<VitalsTrendsModal patient={PATIENT} onClose={onClose} />);
        await screen.findByText('118/76');
        await user.click(screen.getByRole('button', { name: /close/i }));
        expect(onClose).toHaveBeenCalled();
    });
});
