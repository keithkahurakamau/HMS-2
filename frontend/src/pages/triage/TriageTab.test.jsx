import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import TriageTab from './TriageTab';

const baseValue = {
    vitals: { weight: '', height: '', bp: '', hr: '', rr: '', temp: '', spo2: '', pain: '', glucose: '' },
    bmi: '--', complaints: [], complaintInput: '', triageNotes: '', acuity: 3,
    hasNotesDraft: false, notesDraftSavedAt: null,
};
const noop = () => {};
const baseOn = {
    setVitals: noop, setComplaintInput: noop, addComplaint: noop, removeComplaint: noop,
    setTriageNotes: noop, setAcuity: noop, onRestoreDraft: noop, onDiscardDraft: noop,
};

describe('TriageTab', () => {
    it('renders the vitals grid, complaint field and acuity picker', () => {
        render(<TriageTab value={baseValue} on={baseOn} />);
        expect(screen.getByLabelText(/BP \(mmHg\)/i)).toBeInTheDocument();
        expect(screen.getByLabelText(/chief complaint/i)).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /Standard/i })).toBeInTheDocument();
    });

    it('edits a vital through the controlled handler', async () => {
        const setVitals = vi.fn();
        const user = userEvent.setup();
        render(<TriageTab value={baseValue} on={{ ...baseOn, setVitals }} />);
        await user.type(screen.getByLabelText(/RBS/i), '5');
        expect(setVitals).toHaveBeenCalledWith(expect.objectContaining({ glucose: '5' }));
    });

    it('picks an acuity level', async () => {
        const setAcuity = vi.fn();
        const user = userEvent.setup();
        render(<TriageTab value={baseValue} on={{ ...baseOn, setAcuity }} />);
        await user.click(screen.getByRole('button', { name: /Emergency/i }));
        expect(setAcuity).toHaveBeenCalledWith(1);
    });
});
