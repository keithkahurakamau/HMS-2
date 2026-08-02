import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import FilesModal from './FilesModal';
import * as api from '../../../api/clinicalFiles';

vi.mock('../../../api/clinicalFiles');
vi.mock('react-hot-toast', () => ({ default: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }) }));

const patient = { patient_id: 7, patient_name: 'Otieno, Sam' };

describe('FilesModal', () => {
    beforeEach(() => vi.clearAllMocks());

    it('lists existing attachments with size', async () => {
        api.listFiles.mockResolvedValue([
            { file_id: 1, filename: 'referral.pdf', size_bytes: 2048, mime: 'application/pdf' },
        ]);
        render(<FilesModal patient={patient} onClose={() => {}} />);
        expect(await screen.findByText('referral.pdf')).toBeInTheDocument();
        expect(screen.getByText('2 KB')).toBeInTheDocument();
    });

    it('shows the empty state when there are no attachments', async () => {
        api.listFiles.mockResolvedValue([]);
        render(<FilesModal patient={patient} onClose={() => {}} />);
        expect(await screen.findByText(/no attachments yet/i)).toBeInTheDocument();
    });

    it('uploads a picked file as a base64 data URL and reloads', async () => {
        api.listFiles.mockResolvedValue([]);
        api.uploadFile.mockResolvedValue({ file_id: 9 });
        const user = userEvent.setup();
        render(<FilesModal patient={patient} recordId={55} onClose={() => {}} />);
        await screen.findByText(/no attachments yet/i);

        const file = new File(['hello'], 'note.txt', { type: 'text/plain' });
        await user.upload(screen.getByLabelText(/choose a file to attach/i), file);

        await waitFor(() => expect(api.uploadFile).toHaveBeenCalledWith(expect.objectContaining({
            patient_id: 7, filename: 'note.txt', mime: 'text/plain', record_id: 55,
            data: expect.stringMatching(/^data:text\/plain;base64,/),
        })));
    });

    it('deletes an attachment', async () => {
        api.listFiles.mockResolvedValue([{ file_id: 1, filename: 'x.txt', size_bytes: 10 }]);
        api.deleteFile.mockResolvedValue({ status: 'deleted' });
        const user = userEvent.setup();
        render(<FilesModal patient={patient} onClose={() => {}} />);
        await user.click(await screen.findByRole('button', { name: /delete x\.txt/i }));
        await waitFor(() => expect(api.deleteFile).toHaveBeenCalledWith(1));
    });
});
