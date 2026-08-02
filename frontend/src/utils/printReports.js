// Printable clinical reports — Visit Summary, Examination Report, All-Visits.
//
// Built over existing encounter data: the Visit Summary and Examination Report
// render the in-progress (or resumed) encounter held in the Clinical Desk;
// All-Visits renders the patient's record list from GET /clinical/records.
// Same conventions as the other templates (printReferral.js): tolerant of
// missing fields, self-contained via printDocument.

import { printDocument, printUtils } from './printDocument';

const { esc, header, footer } = printUtils;

const orDash = (v) => (v != null && v !== '' ? esc(v) : '—');
const fmtDate = (v) => {
  if (!v) return '—';
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' });
};

const patientPanel = (patient = {}) => `
  <div class="panel">
    <h3>Patient</h3>
    <div class="grid-2">
      <div class="field"><div class="label">Name</div><div class="value">${orDash(patient.patient_name)}</div></div>
      <div class="field"><div class="label">OP Number</div><div class="value">${orDash(patient.outpatient_no)}</div></div>
      <div class="field"><div class="label">Age / Sex</div><div class="value">${orDash(patient.age)} / ${orDash(patient.gender)}</div></div>
      <div class="field"><div class="label">Allergies</div><div class="value">${orDash(patient.allergies)}</div></div>
    </div>
  </div>`;

const vitalsPanel = (v = {}, bmi) => `
  <div class="panel">
    <h3>Vital signs</h3>
    <div class="grid-3">
      <div class="field"><div class="label">BP</div><div class="value">${orDash(v.bp)}</div></div>
      <div class="field"><div class="label">HR</div><div class="value">${orDash(v.hr)}</div></div>
      <div class="field"><div class="label">Resp</div><div class="value">${orDash(v.rr)}</div></div>
      <div class="field"><div class="label">Temp (°C)</div><div class="value">${orDash(v.temp)}</div></div>
      <div class="field"><div class="label">SpO₂ (%)</div><div class="value">${orDash(v.spo2)}</div></div>
      <div class="field"><div class="label">RBS</div><div class="value">${orDash(v.glucose)}</div></div>
      <div class="field"><div class="label">Weight (kg)</div><div class="value">${orDash(v.weight)}</div></div>
      <div class="field"><div class="label">Height (cm)</div><div class="value">${orDash(v.height)}</div></div>
      <div class="field"><div class="label">BMI</div><div class="value">${orDash(bmi)}</div></div>
    </div>
  </div>`;

const listPanel = (title, items = []) => {
  const clean = (items || []).filter((i) => i != null && String(i).trim() !== '');
  const body = clean.length
    ? `<ol style="margin:6px 0 0;padding-left:20px;">${clean.map((i) => `<li>${esc(i)}</li>`).join('')}</ol>`
    : '<div class="value">—</div>';
  return `<div class="panel"><h3>${esc(title)}</h3>${body}</div>`;
};

const impressionsPanel = (encounter = {}) => {
  const codes = (encounter.icdCodes || []).map((c) => c.code ? `${c.code} — ${c.description}` : c.description);
  const freeText = (encounter.diagnosis || '').trim();
  const parts = [...codes];
  if (freeText) parts.push(freeText);
  return listPanel('Impressions / diagnosis', parts);
};

const doctorFollowUp = (encounter = {}) => `
  <div class="panel">
    <h3>Attending &amp; follow-up</h3>
    <div class="grid-2">
      <div class="field"><div class="label">Clinician</div><div class="value">${orDash(encounter.doctorName)}</div></div>
      <div class="field"><div class="label">Visit date</div><div class="value">${fmtDate(encounter.date)}</div></div>
      <div class="field"><div class="label">Next follow-up</div><div class="value">${encounter.followUp?.appointment_date ? fmtDate(encounter.followUp.appointment_date) : '—'}</div></div>
    </div>
  </div>`;

/** Full visit summary — everything captured this encounter. */
export const printVisitSummary = ({ patient = {}, encounter = {} }) => {
  const meds = (encounter.medications || []).filter((m) => (m.drug || '').trim());
  const medRows = meds.length
    ? meds.map((m, i) => `
        <tr>
          <td>${i + 1}</td>
          <td>${orDash(m.drug)}</td>
          <td>${orDash(m.formulation)}</td>
          <td>${orDash(m.dosage)}</td>
          <td>${orDash(m.frequency)}</td>
          <td>${orDash(m.duration)}</td>
        </tr>`).join('')
    : '<tr><td colspan="6" style="text-align:center;color:#64748b;">No medications prescribed</td></tr>';

  const body = `
    ${header({ docType: 'Visit Summary', docNumber: '—' })}
    <h1 class="doc-title">Visit Summary</h1>
    ${patientPanel(patient)}
    ${doctorFollowUp(encounter)}
    ${vitalsPanel(encounter.vitals, encounter.bmi)}
    ${listPanel('Chief complaint(s)', encounter.complaints)}
    ${encounter.hpi ? `<div class="panel"><h3>History of present illness</h3><div class="value">${esc(encounter.hpi)}</div></div>` : ''}
    ${listPanel('Physical examination', encounter.physicalExams)}
    ${impressionsPanel(encounter)}
    <div class="panel">
      <h3>Medications</h3>
      <table class="line-items">
        <thead><tr><th>#</th><th>Drug</th><th>Formulation</th><th>Dosage</th><th>Frequency</th><th>Duration</th></tr></thead>
        <tbody>${medRows}</tbody>
      </table>
    </div>
    ${footer('Visit summary — for the patient’s records.')}
  `;
  printDocument('Visit Summary', body);
};

/** Examination-focused report — vitals, findings, impressions. */
export const printExaminationReport = ({ patient = {}, encounter = {} }) => {
  const body = `
    ${header({ docType: 'Examination Report', docNumber: '—' })}
    <h1 class="doc-title">Examination Report</h1>
    ${patientPanel(patient)}
    ${doctorFollowUp(encounter)}
    ${vitalsPanel(encounter.vitals, encounter.bmi)}
    ${listPanel('Chief complaint(s)', encounter.complaints)}
    ${listPanel('Physical examination findings', encounter.physicalExams)}
    ${impressionsPanel(encounter)}
    ${footer('Examination report.')}
  `;
  printDocument('Examination Report', body);
};

/** All-visits register — the patient's full record list. */
export const printAllVisits = ({ patient = {}, visits = [] }) => {
  const rows = (visits || []).length
    ? visits.map((v) => `
        <tr>
          <td>${fmtDate(v.created_at || v.date)}</td>
          <td>${orDash(v.chief_complaint)}</td>
          <td>${orDash(v.icd10_code)}</td>
          <td>${orDash(v.blood_pressure)}</td>
          <td>${orDash(v.record_status)}</td>
        </tr>`).join('')
    : '<tr><td colspan="5" style="text-align:center;color:#64748b;">No recorded visits</td></tr>';

  const body = `
    ${header({ docType: 'Visit History', docNumber: '—' })}
    <h1 class="doc-title">All Visits</h1>
    ${patientPanel(patient)}
    <div class="panel">
      <h3>Visits (${(visits || []).length})</h3>
      <table class="line-items">
        <thead><tr><th>Date</th><th>Chief complaint</th><th>ICD-10</th><th>BP</th><th>Status</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
    ${footer('Chronological visit register.')}
  `;
  printDocument('All Visits', body);
};

/** Laboratory report — the patient's ordered tests and any results. */
export const printLabReport = ({ patient = {}, tests = [] }) => {
  const rows = (tests || []).length
    ? tests.map((t) => `
        <tr>
          <td>${orDash(t.test_name)}</td>
          <td>${orDash(t.status)}</td>
          <td>${orDash(t.result_summary)}</td>
          <td>${fmtDate(t.created_at || t.ordered_at)}</td>
        </tr>`).join('')
    : '<tr><td colspan="4" style="text-align:center;color:#64748b;">No lab tests</td></tr>';

  const body = `
    ${header({ docType: 'Laboratory Report', docNumber: '—' })}
    <h1 class="doc-title">Laboratory Report</h1>
    ${patientPanel(patient)}
    <div class="panel">
      <h3>Tests (${(tests || []).length})</h3>
      <table class="line-items">
        <thead><tr><th>Test</th><th>Status</th><th>Result</th><th>Ordered</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
    ${footer('Laboratory report — for the patient’s records.')}
  `;
  printDocument('Laboratory Report', body);
};

/** Theatre report — the patient's surgical cases. */
export const printTheatreReport = ({ patient = {}, cases = [] }) => {
  const rows = (cases || []).length
    ? cases.map((c) => `
        <tr>
          <td>${orDash(c.procedure_name)}</td>
          <td>${orDash(c.procedure_code)}</td>
          <td>${orDash(c.diagnosis)}</td>
          <td>${orDash(c.priority)}</td>
          <td>${orDash(c.status)}</td>
          <td>${fmtDate(c.scheduled_at)}</td>
        </tr>`).join('')
    : '<tr><td colspan="6" style="text-align:center;color:#64748b;">No surgical cases</td></tr>';

  const body = `
    ${header({ docType: 'Theatre Report', docNumber: '—' })}
    <h1 class="doc-title">Theatre Report</h1>
    ${patientPanel(patient)}
    <div class="panel">
      <h3>Surgical cases (${(cases || []).length})</h3>
      <table class="line-items">
        <thead><tr><th>Procedure</th><th>Code</th><th>Diagnosis</th><th>Priority</th><th>Status</th><th>Scheduled</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
    ${footer('Theatre report — for the patient’s records.')}
  `;
  printDocument('Theatre Report', body);
};
