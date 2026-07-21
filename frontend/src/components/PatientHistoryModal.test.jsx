import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../test/renderWithProviders';

vi.mock('../api/client', () => ({
    apiClient: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
    isTenantRedirect: vi.fn(() => false),
}));

const navigateMock = vi.fn();
vi.mock('react-router-dom', async () => {
    const actual = await vi.importActual('react-router-dom');
    return { ...actual, useNavigate: () => navigateMock };
});

import { apiClient } from '../api/client';
import PatientHistoryModal from './PatientHistoryModal';

const CHART = {
    patient_id: 42,
    patient_name: 'Amina Wanjiru',
    opd_number: 'OP-0042',
    blood_group: 'O+',
    surgical_history: [
        { entry_id: 1, title: 'Appendectomy', description: 'Uncomplicated, 2019.', status: 'Resolved', severity: 'N/A', is_sensitive: false },
    ],
    family_history: [],
    social_history: [],
    immunizations: [],
    allergies: [],
    chronic_conditions: [],
    past_medical_events: [],
    obstetric_history: [],
    mental_health: [],
    recent_visits: [],
};

beforeEach(() => {
    vi.clearAllMocks();
});

describe('PatientHistoryModal', () => {
    it('fetches the chart and renders the patient header + sections', async () => {
        apiClient.get.mockResolvedValue({ data: CHART });
        renderWithProviders(<PatientHistoryModal patientId={42} onClose={() => {}} />);
        expect(await screen.findByText('Amina Wanjiru')).toBeInTheDocument();
        expect(apiClient.get).toHaveBeenCalledWith('/medical-history/42/chart');
        expect(screen.getByText('Surgical History')).toBeInTheDocument();
    });

    it('expands only the requested section when initialSection is set', async () => {
        apiClient.get.mockResolvedValue({ data: CHART });
        renderWithProviders(<PatientHistoryModal patientId={42} initialSection="SURGICAL_HISTORY" onClose={() => {}} />);
        expect(await screen.findByText('Appendectomy')).toBeInTheDocument();
        // Family History exists as a collapsed section header but its (empty) body shouldn't be open.
        expect(screen.queryByText(/no family history entries recorded/i)).not.toBeInTheDocument();
    });

    it('expands every section when no initialSection is given (full chart)', async () => {
        apiClient.get.mockResolvedValue({ data: CHART });
        renderWithProviders(<PatientHistoryModal patientId={42} onClose={() => {}} />);
        expect(await screen.findByText('Appendectomy')).toBeInTheDocument();
        expect(screen.getByText(/no family history entries recorded/i)).toBeInTheDocument();
    });

    it('"Open full record" navigates to the Medical History page and closes the popup', async () => {
        const user = userEvent.setup();
        const onClose = vi.fn();
        apiClient.get.mockResolvedValue({ data: CHART });
        renderWithProviders(<PatientHistoryModal patientId={42} initialSection="SURGICAL_HISTORY" onClose={onClose} />);
        await screen.findByText('Amina Wanjiru');
        await user.click(screen.getByRole('button', { name: /open full record/i }));
        expect(navigateMock).toHaveBeenCalledWith('/app/medical-history?patient_id=42&entry_type=SURGICAL_HISTORY');
        expect(onClose).toHaveBeenCalled();
    });

    it('shows an error state and never crashes when the chart fails to load', async () => {
        apiClient.get.mockRejectedValue({ response: { data: { detail: 'Access denied' } } });
        renderWithProviders(<PatientHistoryModal patientId={42} onClose={() => {}} />);
        expect(await screen.findByText(/could not load this patient's history/i)).toBeInTheDocument();
    });
});
