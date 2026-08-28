import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../test/renderWithProviders';
import QueuePatientsModal from './QueuePatientsModal';

const minutesAgo = (m) => new Date(Date.now() - m * 60000).toISOString();

const QUEUE = [
    { queue_id: 1, patient_name: 'Aisha Mwangi', outpatient_no: 'OP-0001', triage_time: 'Triage', joined_at: minutesAgo(12), priority: 'Critical' },
    { queue_id: 2, patient_name: 'Brian Kamau', outpatient_no: 'OP-0002', triage_time: 'Reception', joined_at: minutesAgo(4), priority: 'Normal' },
    { queue_id: 3, patient_name: 'Cynthia Wanjiru', outpatient_no: 'OP-0003', triage_time: 'Triage', joined_at: minutesAgo(30), priority: 'High' },
];

const setup = (props = {}) => {
    const handlers = {
        onClose: vi.fn(), onSelectPatient: vi.fn(),
        onRemoveFromQueue: vi.fn(), onClearQueue: vi.fn(),
    };
    renderWithProviders(
        <QueuePatientsModal queue={QUEUE} department="Consultation" {...handlers} {...props} />,
    );
    return handlers;
};

beforeEach(() => vi.clearAllMocks());

describe('listing the queue', () => {
    it('shows every waiting patient, not a truncated few', () => {
        setup();
        for (const p of QUEUE) expect(screen.getByText(p.patient_name)).toBeInTheDocument();
        for (const p of QUEUE) expect(screen.getByText(p.outpatient_no)).toBeInTheDocument();
    });

    it('titles itself with the department display name', () => {
        setup();
        // Canonical "Consultation" surfaces as "Clinical Desk" everywhere.
        expect(screen.getByRole('heading', { name: /Clinical Desk/i })).toBeInTheDocument();
    });

    it('flags non-routine priorities', () => {
        setup();
        expect(screen.getByText('Critical')).toBeInTheDocument();
        expect(screen.getByText('High')).toBeInTheDocument();
        expect(screen.queryByText('Normal')).not.toBeInTheDocument();
    });

    it('says so when nobody is waiting', () => {
        setup({ queue: [] });
        expect(screen.getByText(/No patients are waiting/i)).toBeInTheDocument();
    });
});

describe('filtering', () => {
    it('narrows by name or OP number', async () => {
        const user = userEvent.setup();
        setup();
        await user.type(screen.getByLabelText(/Filter queued patients/i), 'Brian');
        expect(screen.getByText('Brian Kamau')).toBeInTheDocument();
        await waitFor(() => expect(screen.queryByText('Aisha Mwangi')).not.toBeInTheDocument());
    });

    it('keeps a filtered row showing its true place in line', async () => {
        const user = userEvent.setup();
        setup();
        await user.type(screen.getByLabelText(/Filter queued patients/i), 'Cynthia');
        // Third in the queue: must not renumber to 1 just because it's alone.
        expect(screen.getByRole('cell', { name: '3' })).toBeInTheDocument();
    });
});

describe('actions', () => {
    it('opens a patient and closes the dialog', async () => {
        const user = userEvent.setup();
        const h = setup();
        await user.click(screen.getByRole('button', { name: /^Aisha Mwangi/ }));
        expect(h.onSelectPatient).toHaveBeenCalledWith(QUEUE[0]);
        expect(h.onClose).toHaveBeenCalled();
    });

    it('removes a single patient', async () => {
        const user = userEvent.setup();
        const h = setup();
        await user.click(screen.getByRole('button', { name: /Remove Brian Kamau from queue/i }));
        expect(h.onRemoveFromQueue).toHaveBeenCalledWith(QUEUE[1]);
    });

    it('requires confirmation before clearing the whole queue', async () => {
        const user = userEvent.setup();
        const h = setup();
        await user.click(screen.getByRole('button', { name: /Remove all from queue/i }));
        // First click only asks: clearing everyone is not undoable from the UI.
        expect(h.onClearQueue).not.toHaveBeenCalled();
        expect(screen.getByText(/Remove all 3 patients/i)).toBeInTheDocument();

        await user.click(screen.getByRole('button', { name: /Yes, remove all/i }));
        expect(h.onClearQueue).toHaveBeenCalledTimes(1);
    });

    it('lets the confirmation be backed out of', async () => {
        const user = userEvent.setup();
        const h = setup();
        await user.click(screen.getByRole('button', { name: /Remove all from queue/i }));
        await user.click(screen.getByRole('button', { name: /Cancel/i }));
        expect(h.onClearQueue).not.toHaveBeenCalled();
        expect(screen.getByRole('button', { name: /Remove all from queue/i })).toBeInTheDocument();
    });

    it('offers no bulk clear on an empty queue', () => {
        setup({ queue: [] });
        expect(screen.queryByRole('button', { name: /Remove all from queue/i })).not.toBeInTheDocument();
    });

    it('disables the confirm while the clear is in flight', async () => {
        const user = userEvent.setup();
        setup({ isClearing: true });
        await user.click(screen.getByRole('button', { name: /Remove all from queue/i }));
        expect(screen.getByRole('button', { name: /Yes, remove all/i })).toBeDisabled();
    });
});
