import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import PickAdmissionModal from './PickAdmissionModal';
import { apiClient } from '../../../api/client';

vi.mock('../../../api/client', () => ({ apiClient: { get: vi.fn() } }));
vi.mock('react-hot-toast', () => ({ default: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }) }));

const BOARD = [
    { id: 1, name: 'Ward A', beds: [
        { id: 10, number: '1', status: 'Occupied', patient: 'Doe, Jane', patient_id: 5, diagnosis: 'Pneumonia' },
        { id: 11, number: '2', status: 'Available', patient: null },
    ] },
];

describe('PickAdmissionModal', () => {
    beforeEach(() => vi.clearAllMocks());

    it('lists only occupied beds and picks one', async () => {
        apiClient.get.mockResolvedValue({ data: BOARD });
        const onPick = vi.fn();
        const user = userEvent.setup();
        render(<PickAdmissionModal onPick={onPick} onClose={() => {}} />);

        expect(await screen.findByText('Doe, Jane')).toBeInTheDocument();
        expect(screen.getByText(/Ward A · Bed 1 · Pneumonia/)).toBeInTheDocument();
        await user.click(screen.getByText('Doe, Jane'));
        expect(onPick).toHaveBeenCalledWith(expect.objectContaining({ patient_id: 5, ward_name: 'Ward A' }));
    });

    it('shows the empty state when no beds are occupied', async () => {
        apiClient.get.mockResolvedValue({ data: [{ id: 1, name: 'Ward A', beds: [{ id: 11, status: 'Available' }] }] });
        render(<PickAdmissionModal onPick={() => {}} onClose={() => {}} />);
        expect(await screen.findByText(/no admitted patients/i)).toBeInTheDocument();
    });
});
