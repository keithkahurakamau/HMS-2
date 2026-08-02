import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('./printDocument', () => ({
    printDocument: vi.fn(),
    printUtils: {
        esc: (s) => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'),
        hospital: () => 'Test Hospital',
        header: ({ docType, docNumber }) => `<div class="hdr">${docType} ${docNumber}</div>`,
        footer: (msg) => `<div class="ftr">${msg}</div>`,
    },
}));

import { printDocument } from './printDocument';
import { printVisitSummary, printExaminationReport, printAllVisits, printLabReport, printTheatreReport } from './printReports';

const PATIENT = { patient_name: 'Asha Mwangi', age: 34, gender: 'F', outpatient_no: 'OP-2025-0001' };
const ENCOUNTER = {
    date: new Date('2026-07-24T09:00:00Z'),
    doctorName: 'Dr. Otieno',
    vitals: { bp: '120/80', hr: '72', temp: '37.1', weight: '70' },
    bmi: '22.9',
    complaints: ['Severe headache'],
    physicalExams: ['Chest: clear'],
    hpi: 'Headache for 3 days',
    diagnosis: 'Tension headache',
    icdCodes: [{ code: 'G44.2', description: 'Tension-type headache' }],
    medications: [{ drug: 'Paracetamol', formulation: 'Tablet', dosage: '1g', frequency: 'TDS', duration: '3 days' }],
    followUp: null,
};

beforeEach(() => vi.clearAllMocks());
const lastBody = () => printDocument.mock.calls.at(-1)[1];

describe('printVisitSummary', () => {
    it('renders patient, vitals, findings, impressions and medications', () => {
        printVisitSummary({ patient: PATIENT, encounter: ENCOUNTER });
        const body = lastBody();
        for (const text of ['Asha Mwangi', 'OP-2025-0001', '120/80', 'Severe headache',
                            'Headache for 3 days', 'Chest: clear', 'G44.2', 'Tension headache', 'Paracetamol']) {
            expect(body).toContain(text);
        }
    });

    it('shows a placeholder when there are no medications', () => {
        printVisitSummary({ patient: PATIENT, encounter: { ...ENCOUNTER, medications: [] } });
        expect(lastBody()).toContain('No medications prescribed');
    });

    it('escapes HTML in free-text fields', () => {
        printVisitSummary({ patient: PATIENT, encounter: { ...ENCOUNTER, hpi: '<script>alert(1)</script>' } });
        expect(lastBody()).not.toContain('<script>');
    });
});

describe('printExaminationReport', () => {
    it('includes findings and impressions but not the medications table', () => {
        printExaminationReport({ patient: PATIENT, encounter: ENCOUNTER });
        const body = lastBody();
        expect(body).toContain('Physical examination findings');
        expect(body).toContain('Tension-type headache');
        expect(body).not.toContain('Paracetamol');
    });
});

describe('printAllVisits', () => {
    it('renders a row per visit and the count', () => {
        const visits = [
            { created_at: '2026-07-01T10:00:00Z', chief_complaint: 'Cough', icd10_code: 'J20.9', blood_pressure: '118/76', record_status: 'Completed' },
            { created_at: '2026-06-15T10:00:00Z', chief_complaint: 'Fever', icd10_code: 'R50.9', blood_pressure: '120/80', record_status: 'Billed' },
        ];
        printAllVisits({ patient: PATIENT, visits });
        const body = lastBody();
        expect(body).toContain('Visits (2)');
        expect(body).toContain('Cough');
        expect(body).toContain('J20.9');
        expect(body).toContain('Fever');
    });

    it('shows an empty-state row when there are no visits', () => {
        printAllVisits({ patient: PATIENT, visits: [] });
        expect(lastBody()).toContain('No recorded visits');
    });
});

describe('printLabReport', () => {
    it('renders a row per test with status and result', () => {
        const tests = [
            { test_name: 'Full Blood Count', status: 'Completed', result_summary: 'WNL', created_at: '2026-07-01T10:00:00Z' },
            { test_name: 'Malaria RDT', status: 'Pending', result_summary: null },
        ];
        printLabReport({ patient: PATIENT, tests });
        const body = lastBody();
        expect(body).toContain('Tests (2)');
        expect(body).toContain('Full Blood Count');
        expect(body).toContain('WNL');
        expect(body).toContain('Malaria RDT');
    });

    it('shows an empty-state row when there are no tests', () => {
        printLabReport({ patient: PATIENT, tests: [] });
        expect(lastBody()).toContain('No lab tests');
    });
});

describe('printTheatreReport', () => {
    it('renders a row per surgical case', () => {
        const cases = [
            { procedure_name: 'Appendectomy', procedure_code: '0DTJ4ZZ', diagnosis: 'Acute appendicitis', priority: 'Emergency', status: 'Completed', scheduled_at: '2026-07-02T08:00:00Z' },
        ];
        printTheatreReport({ patient: PATIENT, cases });
        const body = lastBody();
        expect(body).toContain('Surgical cases (1)');
        expect(body).toContain('Appendectomy');
        expect(body).toContain('Acute appendicitis');
    });

    it('shows an empty-state row when there are no cases', () => {
        printTheatreReport({ patient: PATIENT, cases: [] });
        expect(lastBody()).toContain('No surgical cases');
    });
});
