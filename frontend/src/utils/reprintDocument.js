// Reprinting previously-issued documents.
//
// MediFleet generates every document on demand from live records rather than
// storing files, so a reprint is just "fetch the payload again and re-render".
// `GET /patients/:id/documents/:kind/:docId` returns exactly the shape the
// matching template in printTemplates.js expects, which keeps this module a
// thin dispatcher: and means reprints automatically pick up the tenant's
// letterhead like any other print.

import { printDocument, printUtils } from './printDocument';
import {
  printInvoice, printPrescription, printLabReport,
  printAdmissionSlip, printRadiologyReport,
} from './printTemplates';

const { esc, header, footer } = printUtils;

const orDash = (v) => (v === null || v === undefined || v === '' ? '-' : esc(v));

const formatDate = (value) => {
  if (!value) return '-';
  const d = new Date(value);
  return Number.isNaN(d.getTime())
    ? esc(value)
    : d.toLocaleDateString('en-KE', { year: 'numeric', month: 'short', day: '2-digit' });
};

/**
 * Visit summary: the clinical encounter itself. Lives here rather than in
 * printTemplates.js because the archive is the only surface that reprints one;
 * the Clinical Desk prints the prescription off the same visit instead.
 */
export const printVisitSummary = ({ patient, record }) => {
  if (!record) return;
  const v = record.vitals || {};
  const vitalRow = (label, value, unit) =>
    (value === null || value === undefined || value === ''
      ? ''
      : `<div class="field"><div class="label">${esc(label)}</div><div class="value">${esc(value)}${unit ? ` ${esc(unit)}` : ''}</div></div>`);

  const vitalsHtml = [
    vitalRow('Blood pressure', v.blood_pressure, 'mmHg'),
    vitalRow('Heart rate', v.heart_rate, 'bpm'),
    vitalRow('Temperature', v.temperature, '°C'),
    vitalRow('SpO2', v.spo2, '%'),
    vitalRow('Weight', v.weight_kg, 'kg'),
  ].filter(Boolean).join('');

  const body = `
    ${header({ docType: 'Visit Summary', docNumber: `VIS-${record.record_id ?? ''}` })}

    <h1 class="doc-title">Visit Summary</h1>
    <div class="doc-subtitle">
      ${formatDate(record.date)}
      ${record.record_status ? ` · <span class="badge">${esc(record.record_status)}</span>` : ''}
    </div>

    <div class="panel">
      <h3>Patient</h3>
      <div class="grid-2">
        <div class="field"><div class="label">Name</div><div class="value">${orDash(patient?.full_name)}</div></div>
        <div class="field"><div class="label">OP Number</div><div class="value">${orDash(patient?.outpatient_no)}</div></div>
        <div class="field"><div class="label">Age / Sex</div><div class="value">${orDash(patient?.age)} / ${orDash(patient?.sex)}</div></div>
        <div class="field"><div class="label">Seen by</div><div class="value">${orDash(record.doctor)}</div></div>
      </div>
    </div>

    ${vitalsHtml ? `<div class="panel"><h3>Vitals</h3><div class="grid-3">${vitalsHtml}</div></div>` : ''}

    <div class="panel">
      <h3>Clinical</h3>
      <div class="field"><div class="label">Chief complaint</div><div class="value">${orDash(record.chief_complaint)}</div></div>
      <div class="field"><div class="label">Diagnosis</div><div class="value">${orDash(record.diagnosis)}</div></div>
      ${record.icd10_code ? `<div class="field"><div class="label">ICD-10</div><div class="value">${esc(record.icd10_code)}</div></div>` : ''}
    </div>

    ${record.assessment_plan
      ? `<div class="panel"><h3>Assessment &amp; plan</h3><div>${esc(record.assessment_plan).replace(/\n/g, '<br/>')}</div></div>`
      : ''}

    ${record.follow_up_date
      ? `<div class="panel"><h3>Follow-up</h3><div class="field"><div class="label">Return on</div><div class="value">${formatDate(record.follow_up_date)}</div></div></div>`
      : ''}

    <div class="signature-block">
      <div class="line">Clinician signature</div>
      <div class="line">Date</div>
    </div>

    ${footer('Reprinted from the patient record.')}
  `;

  printDocument(`Visit summary VIS-${record.record_id ?? ''}`, body);
};

/** Maps a document kind to the template that renders it. */
const RENDERERS = {
  invoice: (p) => printInvoice(p),
  prescription: (p) => printPrescription(p),
  lab_report: (p) => printLabReport(p),
  radiology_report: (p) => printRadiologyReport(p),
  admission: (p) => printAdmissionSlip(p),
  visit_summary: (p) => printVisitSummary(p),
};

export const REPRINTABLE_KINDS = Object.keys(RENDERERS);

/**
 * Fetches a previously-issued document and prints it.
 *
 * The popup is opened by the template *after* the await resolves. Browsers
 * normally block that, so callers must keep this on a direct user gesture and
 * accept the popup-blocked fallback (printDocument drops to a hidden iframe).
 *
 * @returns {Promise<boolean>} false when the kind is unknown, callers surface
 *   the error; the server is the authority on which kinds exist.
 */
export async function reprintPatientDocument(apiClient, patientId, kind, docId) {
  const render = RENDERERS[kind];
  if (!render) return false;
  const res = await apiClient.get(`/patients/${patientId}/documents/${kind}/${docId}`);
  render(res.data?.payload);
  return true;
}
