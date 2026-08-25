import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../test/renderWithProviders';

vi.mock('../api/client', () => ({
    apiClient: { get: vi.fn() },
    isTenantRedirect: vi.fn(() => false),
}));
vi.mock('react-hot-toast', () => ({ default: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }) }));

import { apiClient } from '../api/client';
import QueueBoard from './QueueBoard';

const minutesAgo = (m) => new Date(Date.now() - m * 60000).toISOString();

const LIVE = [
    {
        queue_id: 101, patient_id: 1, patient_name: 'Aisha Mwangi', outpatient_no: 'OP-0001',
        scheme: 'NHIF', from_department: 'Triage', to_department: 'Consultation', department: 'Consultation',
        acuity_level: 2, status: 'Waiting', joined_at: minutesAgo(12), assigned_to: 'Dr. Otieno',
    },
    {
        queue_id: 102, patient_id: 2, patient_name: 'Brian Kamau', outpatient_no: 'OP-0002',
        scheme: 'Cash', from_department: null, to_department: 'Triage', department: 'Triage',
        acuity_level: 3, status: 'Waiting', joined_at: minutesAgo(3), assigned_to: null,
    },
];

const DAY = {
    window: { start: '2026-08-20T00:00:00+00:00', end: '2026-08-21T00:00:00+00:00' },
    total_patients: 1, dealt_with: 1, still_active: 0,
    patients: [{
        patient_id: 1, patient_name: 'Aisha Mwangi', outpatient_no: 'OP-0001', scheme: 'NHIF',
        dealt_with: true, still_active: false, stops: 2,
        departments: ['Triage', 'Consultation'],
        first_seen: minutesAgo(120), last_seen: minutesAgo(60),
        footprint: [
            { queue_id: 1, department: 'Triage', status: 'Completed', joined_at: minutesAgo(120), completed_at: minutesAgo(110), duration_seconds: 600, handled_by: 'Nurse Jane' },
            { queue_id: 2, department: 'Consultation', status: 'Completed', joined_at: minutesAgo(105), completed_at: minutesAgo(60), duration_seconds: 2700, handled_by: 'Dr. Otieno' },
        ],
    }],
};

beforeEach(() => {
    vi.clearAllMocks();
    apiClient.get.mockImplementation((url) => {
        if (url === '/queue/live') return Promise.resolve({ data: LIVE });
        if (url === '/queue/day') return Promise.resolve({ data: DAY });
        return Promise.resolve({ data: [] });
    });
});

describe('QueueBoard — live queue', () => {
    it('loads the live board and shows Q.No, scheme, and from→to rooms', async () => {
        renderWithProviders(<QueueBoard />);

        await waitFor(() => expect(apiClient.get).toHaveBeenCalledWith('/queue/live'));

        expect(await screen.findByText('Aisha Mwangi')).toBeInTheDocument();
        expect(screen.getByText('#101')).toBeInTheDocument();
        expect(screen.getByText('NHIF')).toBeInTheDocument();
        // from → to rooms rendered with the unified display label
        // (canonical "Consultation" shows as "Clinical Desk").
        expect(screen.getAllByText('Clinical Desk').length).toBeGreaterThan(0);
        expect(screen.getByText('Dr. Otieno')).toBeInTheDocument();
        // unclaimed row surfaces its placeholder
        expect(screen.getByText(/Unclaimed/i)).toBeInTheDocument();
    });

    it('filters the live board by department', async () => {
        const user = userEvent.setup();
        renderWithProviders(<QueueBoard />);
        expect(await screen.findByText('Aisha Mwangi')).toBeInTheDocument();

        // Click the "Triage" department chip → only Brian (Triage) remains.
        await user.click(screen.getByRole('button', { name: /^Triage/ }));
        await waitFor(() => expect(screen.queryByText('Aisha Mwangi')).not.toBeInTheDocument());
        expect(screen.getByText('Brian Kamau')).toBeInTheDocument();
    });
});

describe('QueueBoard — day footprints', () => {
    it('switches to the Day tab and shows a patient footprint trail', async () => {
        const user = userEvent.setup();
        renderWithProviders(<QueueBoard />);
        await screen.findByText('Aisha Mwangi'); // live loaded first

        await user.click(screen.getByRole('tab', { name: /Footprints/i }));

        await waitFor(() => expect(apiClient.get).toHaveBeenCalledWith('/queue/day', expect.objectContaining({
            params: expect.objectContaining({ date: expect.any(String) }),
        })));

        // Summary + patient row.
        expect(await screen.findByText(/1 dealt with/i)).toBeInTheDocument();
        const patientBtn = await screen.findByRole('button', { name: /Aisha Mwangi/i });
        await user.click(patientBtn); // expand the footprint

        // Footprint stops with handler names.
        expect(await screen.findByText(/by Nurse Jane/i)).toBeInTheDocument();
        expect(screen.getByText(/by Dr. Otieno/i)).toBeInTheDocument();
    });
});
