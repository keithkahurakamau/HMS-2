import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('./printTemplates', () => ({
    printInvoice: vi.fn(),
    printPrescription: vi.fn(),
    printLabReport: vi.fn(),
    printAdmissionSlip: vi.fn(),
    printRadiologyReport: vi.fn(),
}));
vi.mock('./printDocument', () => ({
    printDocument: vi.fn(),
    printUtils: {
        esc: (v) => String(v ?? ''),
        header: () => '<div class="doc-header"></div>',
        footer: () => '<div class="footer"></div>',
    },
}));

import { reprintPatientDocument, printVisitSummary, REPRINTABLE_KINDS } from './reprintDocument';
import { printDocument } from './printDocument';
import {
    printInvoice, printPrescription, printLabReport,
    printAdmissionSlip, printRadiologyReport,
} from './printTemplates';

const client = (payload) => ({ get: vi.fn().mockResolvedValue({ data: { payload } }) });

beforeEach(() => vi.clearAllMocks());

describe('reprint dispatch', () => {
    it.each([
        ['invoice', printInvoice],
        ['prescription', printPrescription],
        ['lab_report', printLabReport],
        ['radiology_report', printRadiologyReport],
        ['admission', printAdmissionSlip],
    ])('routes %s to its template', async (kind, template) => {
        const payload = { marker: kind };
        const api = client(payload);
        await expect(reprintPatientDocument(api, 7, kind, 42)).resolves.toBe(true);
        expect(api.get).toHaveBeenCalledWith(`/patients/7/documents/${kind}/42`);
        expect(template).toHaveBeenCalledWith(payload);
    });

    it('renders a visit summary without a printTemplates entry', async () => {
        const api = client({ patient: { full_name: 'A B' }, record: { record_id: 9 } });
        await expect(reprintPatientDocument(api, 7, 'visit_summary', 9)).resolves.toBe(true);
        expect(printDocument).toHaveBeenCalled();
    });

    it('reports an unknown kind instead of calling the API', async () => {
        const api = client({});
        await expect(reprintPatientDocument(api, 7, 'not_a_kind', 1)).resolves.toBe(false);
        expect(api.get).not.toHaveBeenCalled();
    });

    it('lets API errors surface so the caller can toast them', async () => {
        const api = { get: vi.fn().mockRejectedValue(new Error('403')) };
        await expect(reprintPatientDocument(api, 7, 'invoice', 1)).rejects.toThrow('403');
        expect(printInvoice).not.toHaveBeenCalled();
    });

    it('covers every kind the server can return', () => {
        expect(new Set(REPRINTABLE_KINDS)).toEqual(new Set([
            'invoice', 'prescription', 'lab_report',
            'radiology_report', 'admission', 'visit_summary',
        ]));
    });
});

describe('visit summary rendering', () => {
    const record = {
        record_id: 12, date: '2026-03-14T09:30:00Z', doctor: 'Dr. Otieno',
        record_status: 'Completed', chief_complaint: 'Headache',
        diagnosis: 'Migraine', icd10_code: 'G43.009',
        assessment_plan: 'Rest\nHydration', follow_up_date: '2026-04-01',
        vitals: { blood_pressure: '118/76', heart_rate: 72, temperature: null, spo2: 98 },
    };
    const patient = { full_name: 'Jane Mwangi', outpatient_no: 'OP-1', age: 38, sex: 'Female' };

    const html = () => {
        printVisitSummary({ patient, record });
        return printDocument.mock.calls[0][1];
    };

    it('prints the clinical detail', () => {
        const out = html();
        expect(out).toContain('Jane Mwangi');
        expect(out).toContain('Migraine');
        expect(out).toContain('G43.009');
        expect(out).toContain('Dr. Otieno');
    });

    it('omits vitals that were never recorded', () => {
        const out = html();
        expect(out).toContain('118/76');
        // temperature is null: no empty "Temperature , " row.
        expect(out).not.toContain('Temperature');
    });

    it('renders multi-line plans as line breaks', () => {
        expect(html()).toContain('Rest<br/>Hydration');
    });

    it('does nothing without a record rather than printing a blank page', () => {
        printVisitSummary({ patient, record: null });
        expect(printDocument).not.toHaveBeenCalled();
    });

    it('titles the document with its reference number', () => {
        printVisitSummary({ patient, record });
        expect(printDocument.mock.calls[0][0]).toBe('Visit summary VIS-12');
    });
});
