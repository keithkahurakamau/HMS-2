import { describe, it, expect } from 'vitest';
import { recordToFormState, splitComplaints } from './encounterResume';

const RECORD = {
    record_id: 42,
    record_status: 'Draft',
    blood_pressure: '124/82',
    heart_rate: 78,
    respiratory_rate: 17,
    temperature: 37.1,
    spo2: 97,
    weight_kg: 65,
    height_cm: 165,
    blood_glucose: 5.9,
    chief_complaint: 'Polyuria; Polydipsia',
    history_of_present_illness: 'Two weeks of increased thirst.',
    physical_examination: 'Chest: clear; Abdomen: soft',
    diagnosis: 'suspected metabolic syndrome',
    icd10_codes: [
        { code: 'E11.9', description: 'Type 2 diabetes mellitus without complications' },
    ],
    treatment_plan: JSON.stringify([
        { drug: 'Metformin', formulation: 'Tablet', dosage: '500 mg', frequency: 'BD (twice daily)', duration: '30 days' },
    ]),
    internal_notes: 'Review fasting glucose next visit',
};

describe('splitComplaints', () => {
    it('splits on semicolons and newlines, dropping empties', () => {
        expect(splitComplaints('Headache; Fever\nCough; ')).toEqual(['Headache', 'Fever', 'Cough']);
    });
    it('returns [] for null/empty', () => {
        expect(splitComplaints(null)).toEqual([]);
        expect(splitComplaints('')).toEqual([]);
    });
});

describe('recordToFormState', () => {
    it('maps a full record onto the Clinical Desk form shape', () => {
        const fs = recordToFormState(RECORD);
        expect(fs.vitals).toEqual({
            weight: 65, height: 165, bp: '124/82', hr: 78,
            rr: 17, temp: 37.1, spo2: 97, glucose: 5.9,
        });
        expect(fs.complaints).toEqual(['Polyuria', 'Polydipsia']);
        expect(fs.physicalExams).toEqual(['Chest: clear', 'Abdomen: soft']);
        expect(fs.hpi).toBe('Two weeks of increased thirst.');
        expect(fs.diagnosisText).toBe('suspected metabolic syndrome');
        expect(fs.internalNotes).toBe('Review fasting glucose next visit');
        expect(fs.icdCodes).toEqual([
            { code: 'E11.9', description: 'Type 2 diabetes mellitus without complications' },
        ]);
        expect(fs.medications).toHaveLength(1);
        expect(fs.medications[0]).toMatchObject({
            drug: 'Metformin', formulation: 'Tablet', dosage: '500 mg',
            frequency: 'BD (twice daily)', duration: '30 days',
        });
        expect(fs.medications[0]._uid).toBeTruthy();
    });

    it('maps null fields to empty-string vitals and empty lists', () => {
        const fs = recordToFormState({ record_id: 1, record_status: 'Draft' });
        expect(fs.vitals).toEqual({
            weight: '', height: '', bp: '', hr: '',
            rr: '', temp: '', spo2: '', glucose: '',
        });
        expect(fs.complaints).toEqual([]);
        expect(fs.physicalExams).toEqual([]);
        expect(fs.medications).toEqual([]);
        expect(fs.icdCodes).toEqual([]);
        expect(fs.hpi).toBe('');
        expect(fs.diagnosisText).toBe('');
        expect(fs.internalNotes).toBe('');
    });

    it('ignores a legacy free-text treatment plan (no structured rows)', () => {
        const fs = recordToFormState({ ...RECORD, treatment_plan: 'Paracetamol as needed' });
        expect(fs.medications).toEqual([]);
    });

    it('blanks the free-text field when diagnosis is just the catalogue-description fallback', () => {
        // buildDiagnosisFields writes the joined descriptions into `diagnosis`
        // when no custom text was entered — resuming shouldn't duplicate them
        // into the free-text input alongside the rebuilt chips.
        const fs = recordToFormState({
            ...RECORD,
            diagnosis: 'Type 2 diabetes mellitus without complications',
        });
        expect(fs.diagnosisText).toBe('');
        expect(fs.icdCodes).toHaveLength(1);
    });
});
