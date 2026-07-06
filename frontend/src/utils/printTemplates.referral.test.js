import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('./printDocument', () => ({
    printDocument: vi.fn(),
    printUtils: {
        // Real escaping — the "escapes HTML" test depends on it.
        esc: (s) => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'),
        hospital: () => 'Test Hospital',
        header: ({ docType, docNumber }) => `<div class="hdr">${docType} ${docNumber}</div>`,
        footer: (msg) => `<div class="ftr">${msg}</div>`,
    },
}));

import { printDocument } from './printDocument';
import { printReferralLetter } from './printTemplates';

const PATIENT = { patient_name: 'Asha Mwangi', age: 34, gender: 'F', outpatient_no: 'OP-2025-0001' };
const REFERRAL = {
    referral_id: 7, specialty: 'Cardiology', target_facility: 'KNH',
    target_clinician: 'Dr. Karanja', urgency: 'Urgent',
    reason: 'Suspected arrhythmia', clinical_summary: 'Palpitations for 2 weeks',
};

beforeEach(() => vi.clearAllMocks());

const lastBody = () => printDocument.mock.calls.at(-1)[1];

describe('printReferralLetter', () => {
    it('typed mode prints every referral field and the patient block', () => {
        printReferralLetter({ mode: 'typed', referral: REFERRAL, patient: PATIENT, doctorName: 'Dr. Otieno' });
        const body = lastBody();
        for (const text of ['Asha Mwangi', 'OP-2025-0001', 'Cardiology', 'KNH', 'Dr. Karanja',
                            'Urgent', 'Suspected arrhythmia', 'Palpitations for 2 weeks', 'Dr. Otieno']) {
            expect(body).toContain(text);
        }
    });

    it('blank-patient mode keeps patient identity but rules the clinical sections', () => {
        printReferralLetter({ mode: 'blank-patient', referral: {}, patient: PATIENT, doctorName: 'Dr. Otieno' });
        const body = lastBody();
        expect(body).toContain('Asha Mwangi');
        expect(body).not.toContain('Cardiology');
        expect(body).toContain('ruled-line');
    });

    it('fully blank mode has no patient data at all', () => {
        printReferralLetter({ mode: 'blank', referral: {}, patient: PATIENT, doctorName: '' });
        const body = lastBody();
        expect(body).not.toContain('Asha Mwangi');
        expect(body).not.toContain('OP-2025-0001');
        expect(body).toContain('ruled-line');
    });

    it('escapes HTML in referral fields', () => {
        printReferralLetter({
            mode: 'typed', patient: PATIENT, doctorName: 'Dr. O',
            referral: { ...REFERRAL, reason: '<script>alert(1)</script>' },
        });
        expect(lastBody()).not.toContain('<script>');
    });
});
