import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import MyAppointmentsModal from './MyAppointmentsModal';
import { apiClient } from '../../../api/client';

vi.mock('../../../api/client', () => ({ apiClient: { get: vi.fn() } }));
vi.mock('react-hot-toast', () => ({ default: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }) }));

describe('MyAppointmentsModal', () => {
    beforeEach(() => vi.clearAllMocks());

    it('loads today\'s appointments for the doctor and picks one', async () => {
        apiClient.get.mockResolvedValue({ data: [
            { appointment_id: 1, patient_name: 'Otieno, Sam', patient_id: 7, appointment_date: '2026-08-02T09:00:00', status: 'Scheduled' },
        ] });
        const onPick = vi.fn();
        const user = userEvent.setup();
        render(<MyAppointmentsModal doctorId={42} onPick={onPick} onClose={() => {}} />);

        await waitFor(() => expect(apiClient.get).toHaveBeenCalledWith('/appointments/', expect.objectContaining({
            params: expect.objectContaining({ doctor_id: 42 }),
        })));
        await user.click(await screen.findByText('Otieno, Sam'));
        expect(onPick).toHaveBeenCalledWith(expect.objectContaining({ appointment_id: 1 }));
    });

    it('shows the empty state', async () => {
        apiClient.get.mockResolvedValue({ data: [] });
        render(<MyAppointmentsModal doctorId={42} onPick={() => {}} onClose={() => {}} />);
        expect(await screen.findByText(/no appointments scheduled/i)).toBeInTheDocument();
    });
});
