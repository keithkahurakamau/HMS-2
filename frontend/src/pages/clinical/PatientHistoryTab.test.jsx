import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import PatientHistoryTab from './PatientHistoryTab';
import { apiClient } from '../../api/client';

vi.mock('../../api/client', () => ({ apiClient: { get: vi.fn() } }));
vi.mock('react-hot-toast', () => ({ default: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }) }));

describe('PatientHistoryTab', () => {
    beforeEach(() => vi.clearAllMocks());

    it('loads and renders previous visits', async () => {
        apiClient.get.mockResolvedValue({ data: [
            { record_id: 1, created_at: '2026-07-01T09:00:00Z', chief_complaint: 'Cough', icd10_code: 'J20.9', blood_pressure: '118/76', record_status: 'Completed' },
        ] });
        render(<PatientHistoryTab patientId={7} onOpenHistory={() => {}} />);
        await waitFor(() => expect(apiClient.get).toHaveBeenCalledWith('/clinical/records/7'));
        expect(await screen.findByText('Cough')).toBeInTheDocument();
        expect(screen.getByText('J20.9')).toBeInTheDocument();
    });

    it('opens a history category', async () => {
        apiClient.get.mockResolvedValue({ data: [] });
        const onOpenHistory = vi.fn();
        const user = userEvent.setup();
        render(<PatientHistoryTab patientId={7} onOpenHistory={onOpenHistory} />);
        await user.click(screen.getByRole('button', { name: /surgical hx/i }));
        expect(onOpenHistory).toHaveBeenCalledWith('SURGICAL_HISTORY');
    });

    it('shows the empty state when there are no visits', async () => {
        apiClient.get.mockResolvedValue({ data: [] });
        render(<PatientHistoryTab patientId={7} onOpenHistory={() => {}} />);
        expect(await screen.findByText(/no recorded visits/i)).toBeInTheDocument();
    });
});
