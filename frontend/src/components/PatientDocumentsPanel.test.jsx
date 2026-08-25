import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../test/renderWithProviders';

vi.mock('../api/client', () => ({
    apiClient: { get: vi.fn() },
    isTenantRedirect: vi.fn(() => false),
}));
vi.mock('react-hot-toast', () => ({
    default: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }),
}));
vi.mock('../utils/reprintDocument', () => ({ reprintPatientDocument: vi.fn() }));

import { apiClient } from '../api/client';
import toast from 'react-hot-toast';
import { reprintPatientDocument } from '../utils/reprintDocument';
import PatientDocumentsPanel from './PatientDocumentsPanel';

const DOCS = [
    { kind: 'invoice', id: 145, title: 'Receipt INV-145', date: '2026-07-23T10:00:00Z', summary: 'KES 12,000.00', status: 'Paid' },
    { kind: 'prescription', id: 58, title: 'Prescription RX-58', date: '2026-06-02T08:00:00Z', summary: '3 items', status: 'Completed' },
    { kind: 'lab_report', id: 105, title: 'Full Blood Count', date: '2026-05-11T14:00:00Z', summary: 'Normal', status: 'Completed' },
];

const mockDocs = (documents) => {
    apiClient.get.mockResolvedValue({
        data: { patient: { full_name: 'Jane Mwangi' }, documents, total: documents.length },
    });
};

beforeEach(() => {
    vi.clearAllMocks();
    reprintPatientDocument.mockResolvedValue(true);
});

describe('loading the archive', () => {
    it('lists every previously issued document', async () => {
        mockDocs(DOCS);
        renderWithProviders(<PatientDocumentsPanel patientId={7} />);

        await waitFor(() => expect(apiClient.get).toHaveBeenCalledWith('/patients/7/documents'));
        expect(await screen.findByText('Receipt INV-145')).toBeInTheDocument();
        expect(screen.getByText('Prescription RX-58')).toBeInTheDocument();
        expect(screen.getByText('Full Blood Count')).toBeInTheDocument();
    });

    it('says so when the patient has no documents', async () => {
        mockDocs([]);
        renderWithProviders(<PatientDocumentsPanel patientId={7} />);
        expect(await screen.findByText(/No documents have been issued/i)).toBeInTheDocument();
    });

    it('surfaces a load failure instead of an empty list', async () => {
        apiClient.get.mockRejectedValue({ response: { data: { detail: 'Access denied.' } } });
        renderWithProviders(<PatientDocumentsPanel patientId={7} />);
        expect(await screen.findByText('Access denied.')).toBeInTheDocument();
    });
});

describe('filtering', () => {
    it('offers one chip per kind actually present', async () => {
        mockDocs(DOCS);
        renderWithProviders(<PatientDocumentsPanel patientId={7} />);
        await screen.findByText('Receipt INV-145');

        expect(screen.getByRole('button', { name: /^All/ })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /Invoices/ })).toBeInTheDocument();
        // No radiology on this patient, so no radiology chip.
        expect(screen.queryByRole('button', { name: /Radiology/ })).not.toBeInTheDocument();
    });

    it('narrows the list to the chosen kind', async () => {
        const user = userEvent.setup();
        mockDocs(DOCS);
        renderWithProviders(<PatientDocumentsPanel patientId={7} />);
        await screen.findByText('Receipt INV-145');

        await user.click(screen.getByRole('button', { name: /Invoices/ }));
        expect(screen.getByText('Receipt INV-145')).toBeInTheDocument();
        await waitFor(() => expect(screen.queryByText('Prescription RX-58')).not.toBeInTheDocument());
    });

    it('hides the filter row when only one kind exists', async () => {
        mockDocs([DOCS[0]]);
        renderWithProviders(<PatientDocumentsPanel patientId={7} />);
        await screen.findByText('Receipt INV-145');
        expect(screen.queryByRole('button', { name: /^All/ })).not.toBeInTheDocument();
    });
});

describe('reprinting', () => {
    it('reprints the document that was clicked', async () => {
        const user = userEvent.setup();
        mockDocs(DOCS);
        renderWithProviders(<PatientDocumentsPanel patientId={7} />);
        await screen.findByText('Receipt INV-145');

        await user.click(screen.getAllByRole('button', { name: /Print/i })[0]);
        expect(reprintPatientDocument).toHaveBeenCalledWith(apiClient, 7, 'invoice', 145);
    });

    it('reports a failed reprint', async () => {
        const user = userEvent.setup();
        mockDocs(DOCS);
        reprintPatientDocument.mockRejectedValue({ response: { data: { detail: 'Gone.' } } });
        renderWithProviders(<PatientDocumentsPanel patientId={7} />);
        await screen.findByText('Receipt INV-145');

        await user.click(screen.getAllByRole('button', { name: /Print/i })[0]);
        await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Gone.'));
    });

    it('re-enables the button after a failure so it can be retried', async () => {
        const user = userEvent.setup();
        mockDocs([DOCS[0]]);
        reprintPatientDocument.mockRejectedValue(new Error('boom'));
        renderWithProviders(<PatientDocumentsPanel patientId={7} />);
        await screen.findByText('Receipt INV-145');

        const btn = screen.getByRole('button', { name: /Print/i });
        await user.click(btn);
        await waitFor(() => expect(btn).not.toBeDisabled());
    });
});
