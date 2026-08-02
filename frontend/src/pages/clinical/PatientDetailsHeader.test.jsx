import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import PatientDetailsHeader from './PatientDetailsHeader';

// Stub the typeahead so we don't exercise the patients API here.
vi.mock('../../components/PatientSearch', () => ({
    default: ({ onSelect }) => (
        <button type="button" onClick={() => onSelect({ patient_id: 3, patient_name: 'Searched, Pat' })}>search-pick</button>
    ),
}));

const QUEUE = [
    { queue_id: 1, patient_id: 5, outpatient_no: 'OP-1', patient_name: 'Doe, Jane', triage_time: '09:00 AM', priority: 'Critical',
      joined_at: new Date(Date.now() - 15 * 60000).toISOString() },
    { queue_id: 2, patient_id: 6, outpatient_no: 'OP-2', patient_name: 'Roe, Sam', triage_time: '09:20 AM', priority: 'Normal',
      joined_at: new Date(Date.now() - 5 * 60000).toISOString() },
];
const ACTIVE = { queue_id: 1, patient_id: 5, patient_name: 'Doe, Jane', outpatient_no: 'OP-1', age: 34, gender: 'F', allergies: 'Penicillin', priority: 'Critical' };

describe('PatientDetailsHeader', () => {
    beforeEach(() => vi.clearAllMocks());

    it('renders the queue table with waiting minutes', () => {
        render(<PatientDetailsHeader queue={QUEUE} onSelectPatient={() => {}} />);
        expect(screen.getByText('Doe, Jane')).toBeInTheDocument();
        expect(screen.getByText('2 waiting')).toBeInTheDocument();
        expect(screen.getByText('15')).toBeInTheDocument(); // mins waiting for row 1
        expect(screen.getByText('OP-2')).toBeInTheDocument();
    });

    it('shows demographics and flags allergies for the active patient', () => {
        render(<PatientDetailsHeader activePatient={ACTIVE} queue={QUEUE} onSelectPatient={() => {}} />);
        expect(screen.getByText('Penicillin')).toBeInTheDocument();
    });

    it('selects a patient from the queue', async () => {
        const onSelect = vi.fn();
        const user = userEvent.setup();
        render(<PatientDetailsHeader queue={QUEUE} onSelectPatient={onSelect} />);
        await user.click(screen.getByText('Roe, Sam'));
        expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ queue_id: 2 }));
    });

    it('selects a patient from the search box', async () => {
        const onSelect = vi.fn();
        const user = userEvent.setup();
        render(<PatientDetailsHeader queue={[]} onSelectPatient={onSelect} />);
        await user.click(screen.getByText('search-pick'));
        expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ patient_id: 3 }));
    });

    it('removes a patient from the queue when the handler is supplied', async () => {
        const onRemove = vi.fn();
        const user = userEvent.setup();
        render(<PatientDetailsHeader queue={QUEUE} onSelectPatient={() => {}} onRemoveFromQueue={onRemove} />);
        await user.click(screen.getByRole('button', { name: /remove doe, jane from queue/i }));
        expect(onRemove).toHaveBeenCalledWith(expect.objectContaining({ queue_id: 1 }));
    });
});
