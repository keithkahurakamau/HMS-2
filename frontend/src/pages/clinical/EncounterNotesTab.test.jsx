import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import EncounterNotesTab from './EncounterNotesTab';

// Stub the ICD picker — it hits the terminology API, out of scope here.
vi.mock('../../components/IcdDiagnosisPicker', () => ({ default: () => <div>icd-picker</div> }));

const baseValue = {
    vitals: { bp: '', hr: '', rr: '', temp: '', spo2: '', glucose: '', weight: '', height: '' },
    bmi: '—',
    complaints: [], complaintInput: '', clinicalNotes: { hpi: '', diagnosis: '', internal_notes: '' },
    physicalExams: [], examInput: '', icdCodes: [], medications: [],
    assessPlan: '', pendingFollowUp: null, chargeConsultation: false, myFee: { amount: 1000 },
};

const noop = () => {};
const baseOn = {
    setVitals: noop, setComplaintInput: noop, addComplaint: noop, removeComplaint: noop,
    setClinicalNotes: noop, setExamInput: noop, addExam: noop, removeExam: noop, setIcdCodes: noop,
    addMedication: noop, updateMedication: noop, removeMedication: noop, onOrderLabs: noop,
    onOrderImaging: noop, onPickFollowUp: noop, setChargeConsultation: noop, onChangeFee: noop,
    onViewTrends: noop, setAssessPlan: noop,
};

describe('EncounterNotesTab', () => {
    it('renders the SOAP sections and vitals grid', () => {
        render(<EncounterNotesTab value={baseValue} on={baseOn} />);
        expect(screen.getByLabelText(/chief complaint/i)).toBeInTheDocument();
        expect(screen.getByLabelText(/history of present illness/i)).toBeInTheDocument();
        expect(screen.getByText('icd-picker')).toBeInTheDocument();
        expect(screen.getByLabelText(/^assessment$/i)).toBeInTheDocument();
    });

    it('edits vitals through the controlled handler', async () => {
        const setVitals = vi.fn();
        const user = userEvent.setup();
        render(<EncounterNotesTab value={baseValue} on={{ ...baseOn, setVitals }} />);
        await user.type(screen.getByLabelText(/BP \(mmHg\)/i), '1');
        expect(setVitals).toHaveBeenCalledWith(expect.objectContaining({ bp: '1' }));
    });

    it('serializes the assessment field into assessment_plan', async () => {
        const setAssessPlan = vi.fn();
        const user = userEvent.setup();
        render(<EncounterNotesTab value={baseValue} on={{ ...baseOn, setAssessPlan }} />);
        await user.type(screen.getByLabelText(/^assessment$/i), 'S');
        expect(setAssessPlan).toHaveBeenCalledWith('Assessment:\nS\n\nPlan:\n');
    });
});
