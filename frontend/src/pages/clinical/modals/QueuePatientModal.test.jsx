import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import QueuePatientModal from './QueuePatientModal';
import { apiClient } from '../../../api/client';

vi.mock('../../../api/client', () => ({ apiClient: { post: vi.fn() } }));
vi.mock('react-hot-toast', () => ({ default: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }) }));
// Stub PatientSearch to a one-click pick so we don't exercise the typeahead here.
vi.mock('../../../components/PatientSearch', () => ({
    default: ({ onSelect }) => (
        <button type="button" onClick={() => onSelect({ patient_id: 7, surname: 'Otieno', other_names: 'Sam' })}>pick-patient</button>
    ),
}));

describe('QueuePatientModal', () => {
    beforeEach(() => vi.clearAllMocks());

    it('posts the picked patient to the consultation queue', async () => {
        apiClient.post.mockResolvedValue({ data: {} });
        const onQueued = vi.fn();
        const user = userEvent.setup();
        render(<QueuePatientModal onQueued={onQueued} onClose={() => {}} />);

        await user.click(screen.getByText('pick-patient'));
        await user.click(screen.getByRole('button', { name: /add to queue/i }));

        await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith('/queue/', expect.objectContaining({
            patient_id: 7, department: 'Consultation', acuity_level: 3,
        })));
        await waitFor(() => expect(onQueued).toHaveBeenCalled());
    });
});
