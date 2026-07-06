import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../api/client', () => ({
    apiClient: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
    isTenantRedirect: vi.fn(() => false),
}));

import { apiClient } from '../api/client';
import VisitHistoryList from './VisitHistoryList';

const VISITS = [
    { record_id: 51, date: '2026-07-01T09:00:00Z', doctor: 'Dr. Otieno',
      chief_complaint: 'cough', diagnosis: 'Acute bronchitis', icd10_code: 'J20.9', record_status: 'Completed' },
    { record_id: 40, date: '2026-05-11T10:00:00Z', doctor: 'Dr. Wanjiru',
      chief_complaint: 'headache', diagnosis: 'Migraine', icd10_code: 'G43.9', record_status: 'Completed' },
];

const DETAIL = {
    record_id: 51, date: '2026-07-01T09:00:00Z', doctor: 'Dr. Otieno', record_status: 'Completed',
    vitals: { blood_pressure: '120/80', heart_rate: 72, respiratory_rate: null, temperature: 36.8,
              spo2: 98, weight_kg: 70, height_cm: 175, calculated_bmi: 22.9, blood_glucose: null },
    chief_complaint: 'cough', history_of_present_illness: 'Productive cough for 3 days',
    review_of_systems: null, physical_examination: 'Chest clear',
    icd10_codes: ['J20.9', 'E11.9'], diagnosis: 'Acute bronchitis; T2DM',
    prescriptions: [{ drug: 'Amoxicillin', formulation: 'caps', dosage: '500mg', frequency: '8h', duration: '5d' }],
    prescription_notes: null, follow_up_date: null, internal_notes: 'watch sugar',
    lab_tests: [{ test_id: 1, test_name: 'FBC', status: 'Completed', result_summary: 'Normal' }],
    radiology: [{ request_id: 3, exam_type: 'Chest X-Ray', status: 'Completed', conclusion: 'Clear' }],
};

beforeEach(() => vi.clearAllMocks());

describe('VisitHistoryList', () => {
    it('lists every visit summary', () => {
        render(<VisitHistoryList visits={VISITS} />);
        expect(screen.getByText(/visit history \(2\)/i)).toBeInTheDocument();
        expect(screen.getByText('Acute bronchitis')).toBeInTheDocument();
        expect(screen.getByText('Migraine')).toBeInTheDocument();
    });

    it('fetches and renders full detail on expand, once', async () => {
        const user = userEvent.setup();
        apiClient.get.mockResolvedValue({ data: DETAIL });
        render(<VisitHistoryList visits={VISITS} />);
        await user.click(screen.getByRole('button', { name: /acute bronchitis/i }));
        await waitFor(() => expect(apiClient.get).toHaveBeenCalledWith('/clinical/record/51'));
        expect(await screen.findByText('120/80')).toBeInTheDocument();
        expect(screen.getByText('Productive cough for 3 days')).toBeInTheDocument();
        expect(screen.getByText('Amoxicillin')).toBeInTheDocument();
        expect(screen.getByText('FBC')).toBeInTheDocument();
        expect(screen.getByText('Chest X-Ray')).toBeInTheDocument();
        expect(screen.getByText('E11.9')).toBeInTheDocument();
        // collapse + re-expand must not refetch
        await user.click(screen.getByRole('button', { name: /acute bronchitis/i }));
        await user.click(screen.getByRole('button', { name: /acute bronchitis/i }));
        expect(apiClient.get).toHaveBeenCalledTimes(1);
    });

    it('shows an inline error with retry when the fetch fails', async () => {
        const user = userEvent.setup();
        apiClient.get.mockRejectedValueOnce(new Error('boom')).mockResolvedValueOnce({ data: DETAIL });
        render(<VisitHistoryList visits={VISITS} />);
        await user.click(screen.getByRole('button', { name: /acute bronchitis/i }));
        expect(await screen.findByText(/could not load/i)).toBeInTheDocument();
        await user.click(screen.getByRole('button', { name: /retry/i }));
        expect(await screen.findByText('120/80')).toBeInTheDocument();
    });

    it('renders the empty state', () => {
        render(<VisitHistoryList visits={[]} />);
        expect(screen.getByText(/no clinical visits recorded/i)).toBeInTheDocument();
    });
});
