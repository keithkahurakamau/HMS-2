import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../api/client', () => ({
    apiClient: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
    isTenantRedirect: vi.fn(() => false),
}));
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }));
vi.mock('../utils/printReferral', () => ({ printReferralLetter: vi.fn() }));
vi.mock('../context/AuthContext', () => ({
    useAuth: () => ({ user: { full_name: 'Dr. Otieno' } }),
}));

import { apiClient } from '../api/client';
import toast from 'react-hot-toast';
import { printReferralLetter } from '../utils/printReferral';
import ReferralModal from './ReferralModal';

const PATIENT = { patient_id: 11, patient_name: 'Asha Mwangi', age: 34, gender: 'F', outpatient_no: 'OP-2025-0001' };
const SAVED = { referral_id: 7, specialty: 'Cardiology', reason: 'Arrhythmia', urgency: 'Routine' };

beforeEach(() => {
    vi.clearAllMocks();
    apiClient.post.mockResolvedValue({ data: SAVED });
});

describe('ReferralModal', () => {
    it('requires specialty and reason before saving', async () => {
        const user = userEvent.setup();
        render(<ReferralModal patient={PATIENT} initialSummary="" onClose={() => {}} />);
        await user.click(screen.getByRole('button', { name: /save & print typed letter/i }));
        expect(apiClient.post).not.toHaveBeenCalled();
        expect(toast.error).toHaveBeenCalled();
    });

    it('saves then prints the typed letter', async () => {
        const user = userEvent.setup();
        render(<ReferralModal patient={PATIENT} initialSummary="T2DM" onClose={() => {}} />);
        await user.type(screen.getByLabelText(/specialty/i), 'Cardiology');
        await user.type(screen.getByLabelText(/reason/i), 'Arrhythmia');
        await user.click(screen.getByRole('button', { name: /save & print typed letter/i }));
        await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith('/referrals/', expect.objectContaining({
            patient_id: 11, specialty: 'Cardiology', reason: 'Arrhythmia', clinical_summary: 'T2DM',
        })));
        expect(printReferralLetter).toHaveBeenCalledWith(expect.objectContaining({
            mode: 'typed', referral: SAVED, doctorName: 'Dr. Otieno',
        }));
    });

    it('save-only does not print', async () => {
        const user = userEvent.setup();
        const onClose = vi.fn();
        render(<ReferralModal patient={PATIENT} initialSummary="" onClose={onClose} />);
        await user.type(screen.getByLabelText(/specialty/i), 'ENT');
        await user.type(screen.getByLabelText(/reason/i), 'Chronic sinusitis');
        await user.click(screen.getByRole('button', { name: /^save referral$/i }));
        await waitFor(() => expect(apiClient.post).toHaveBeenCalled());
        expect(printReferralLetter).not.toHaveBeenCalled();
        expect(onClose).toHaveBeenCalled();
    });

    it('blank prints never hit the API', async () => {
        const user = userEvent.setup();
        render(<ReferralModal patient={PATIENT} initialSummary="" onClose={() => {}} />);
        await user.click(screen.getByRole('button', { name: /blank \(with patient info\)/i }));
        expect(printReferralLetter).toHaveBeenCalledWith(expect.objectContaining({ mode: 'blank-patient', patient: PATIENT }));
        await user.click(screen.getByRole('button', { name: /fully blank/i }));
        expect(printReferralLetter).toHaveBeenCalledWith(expect.objectContaining({ mode: 'blank' }));
        expect(apiClient.post).not.toHaveBeenCalled();
    });

    it('keeps the modal open and shows the backend detail on save failure', async () => {
        const user = userEvent.setup();
        apiClient.post.mockRejectedValueOnce({ response: { data: { detail: 'Patient not found.' } } });
        const onClose = vi.fn();
        render(<ReferralModal patient={PATIENT} initialSummary="" onClose={onClose} />);
        await user.type(screen.getByLabelText(/specialty/i), 'ENT');
        await user.type(screen.getByLabelText(/reason/i), 'x');
        await user.click(screen.getByRole('button', { name: /^save referral$/i }));
        await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Patient not found.'));
        expect(onClose).not.toHaveBeenCalled();
    });
});
