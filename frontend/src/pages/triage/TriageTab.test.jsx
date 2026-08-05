import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import TriageTab from './TriageTab';

const baseValue = {
    vitals: { weight: '', height: '', bp: '', hr: '', rr: '', temp: '', spo2: '', pain: '', glucose: '' },
    bmi: '--', complaints: [], complaintInput: '', triageNotes: '', acuity: 3,
    systemicExam: [], procedures: [], hasNotesDraft: false, notesDraftSavedAt: null,
};
const noop = () => {};
const baseOn = {
    setVitals: noop, setComplaintInput: noop, addComplaint: noop, removeComplaint: noop,
    setTriageNotes: noop, setAcuity: noop, onRestoreDraft: noop, onDiscardDraft: noop,
    addSystemic: noop, removeSystemic: noop, addProcedure: noop, removeProcedure: noop,
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

    it('adds a systemic-examination finding with the anomalous flag', async () => {
        const addSystemic = vi.fn();
        const user = userEvent.setup();
        render(<TriageTab value={baseValue} on={{ ...baseOn, addSystemic }} />);
        await user.type(screen.getByLabelText(/Body System/i), 'Respiratory');
        await user.click(screen.getByLabelText(/Is anomalous/i));
        // Add buttons in DOM order: complaint, systemic, procedure → systemic = [1].
        await user.click(screen.getAllByRole('button', { name: /^Add$/i })[1]);
        expect(addSystemic).toHaveBeenCalledWith(expect.objectContaining({ body_system: 'Respiratory', is_anomalous: true }));
    });

    it('adds a procedure', async () => {
        const addProcedure = vi.fn();
        const user = userEvent.setup();
        render(<TriageTab value={baseValue} on={{ ...baseOn, addProcedure }} />);
        await user.type(screen.getByLabelText(/^Procedure$/i), 'Dressing');
        const addButtons = screen.getAllByRole('button', { name: /^Add$/i });
        await user.click(addButtons[addButtons.length - 1]); // last Add = procedures
        expect(addProcedure).toHaveBeenCalledWith(expect.objectContaining({ procedure: 'Dressing' }));
    });
});
