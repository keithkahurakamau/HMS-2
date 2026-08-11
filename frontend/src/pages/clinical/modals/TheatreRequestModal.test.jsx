import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import TheatreRequestModal from './TheatreRequestModal';
import { apiClient } from '../../../api/client';

vi.mock('../../../api/client', () => ({ apiClient: { post: vi.fn() } }));
vi.mock('react-hot-toast', () => ({ default: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }) }));

const patient = { patient_id: 7, patient_name: 'Otieno, Sam' };

describe('TheatreRequestModal', () => {
    beforeEach(() => vi.clearAllMocks());

    it('creates a theatre case for the patient', async () => {
        apiClient.post.mockResolvedValue({ data: {} });
        const user = userEvent.setup();
        render(<TheatreRequestModal patient={patient} onClose={() => {}} />);

        await user.type(screen.getByLabelText(/^Procedure$/i), 'Appendectomy');
        await user.selectOptions(screen.getByLabelText(/Priority/i), 'Emergency');
        await user.click(screen.getByRole('button', { name: /create request/i }));

        await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith('/theatre/cases', expect.objectContaining({
            patient_id: 7, procedure_name: 'Appendectomy', priority: 'Emergency',
        })));
    });

    it('requires a procedure name', async () => {
        const user = userEvent.setup();
        render(<TheatreRequestModal patient={patient} onClose={() => {}} />);
        await user.click(screen.getByRole('button', { name: /create request/i }));
        expect(apiClient.post).not.toHaveBeenCalled();
    });
});
