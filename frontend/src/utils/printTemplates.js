
// Printable document templates.
//
// Each function takes the page's existing data shape and produces a body HTML
// fragment to hand to printDocument(). Templates are intentionally tolerant of
// missing fields — they render '—' rather than throwing if optional values
// are absent.

import { printDocument, printUtils } from './printDocument';

const { esc, header, footer } = printUtils;

const orDash = (value) => {
  if (value === null || value === undefined || value === '') return '—';
  return esc(value);
};

const formatKES = (n) => {
  const num = Number(n) || 0;
  return num.toLocaleString('en-KE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};

const formatDate = (value) => {
  if (!value) return '—';
  const d = new Date(value);
  if (isNaN(d.getTime())) return esc(value);
  return d.toLocaleDateString('en-KE', { year: 'numeric', month: 'short', day: '2-digit' });
};

// =====================================================================
// 1. INVOICE / PAYMENT RECEIPT
// =====================================================================
export const printInvoice = (invoice) => {
  if (!invoice) return;

  const items = invoice.items || [];
  const total = Number(invoice.total_amount) || 0;
  const paid = Number(invoice.amount_paid) || 0;
  const balance = total - paid;
  const isReceipt = balance <= 0;
  const docType = isReceipt ? 'Payment Receipt' : 'Invoice';

  const itemsHtml = items.length ? items.map((item) => `
    <tr>
      <td>${esc(item.description || '')}</td>
      <td>${esc(item.item_type || '')}</td>
      <td class="amount">${formatKES(item.amount)}</td>
    </tr>
  `).join('') : `<tr><td colspan="3" style="text-align:center;color:#94a3b8;">No line items recorded.</td></tr>`;

  const body = `
    ${header({ docType, docNumber: `INV-${invoice.invoice_id ?? '—'}` })}

    <h1 class="doc-title">${esc(docType)}</h1>
    <div class="doc-subtitle">
      Status:
      <span class="badge ${isReceipt ? 'paid' : 'pending'}">${esc(invoice.status || (isReceipt ? 'Paid' : 'Pending'))}</span>
    </div>

    <div class="panel">
      <h3>Patient</h3>
      <div class="grid-2">
        <div class="field"><div class="label">Name</div><div class="value">${orDash(invoice.patient_name)}</div></div>
        <div class="field"><div class="label">OP Number</div><div class="value">${orDash(invoice.patient_opd)}</div></div>
        <div class="field"><div class="label">Invoice ID</div><div class="value">INV-${orDash(invoice.invoice_id)}</div></div>
        <div class="field"><div class="label">Billing Date</div><div class="value">${formatDate(invoice.billing_date || invoice.created_at)}</div></div>
      </div>
    </div>

    <table class="line-items">
      <thead>
        <tr>
          <th>Description</th>
          <th>Category</th>
          <th class="amount">Amount (KES)</th>
        </tr>
      </thead>
      <tbody>
        ${itemsHtml}
      </tbody>
    </table>

    <div class="totals">
      <div class="row"><span>Subtotal</span><span>${formatKES(total)}</span></div>
      ${paid > 0 ? `<div class="row"><span>Amount Paid</span><span>− ${formatKES(paid)}</span></div>` : ''}
      <div class="row grand">
        <span>${isReceipt ? 'Total Paid' : 'Balance Due'}</span>
        <span>KES ${formatKES(isReceipt ? paid : balance)}</span>
      </div>
    </div>

    <div class="signature-block">
      <div class="line">Cashier Signature</div>
      <div class="line">Patient / Guarantor Signature</div>
    </div>

    ${footer(isReceipt ? 'Thank you for your payment.' : 'Please settle the outstanding balance at the cashier.')}
  `;

  printDocument(`${docType} INV-${invoice.invoice_id ?? ''}`, body);
};

// =====================================================================
// 2. PRESCRIPTION
// =====================================================================
export const printPrescription = ({ patient, doctor, items = [], notes, recordId }) => {
  if (!patient) return;

  const itemsHtml = items.length ? items.map((it) => `
    <tr>
      <td><b>${esc(it.drug_name || it.name || '')}</b></td>
      <td>${orDash(it.dosage)}</td>
      <td>${orDash(it.frequency)}</td>
      <td>${orDash(it.duration)}</td>
      <td>${orDash(it.route || it.notes)}</td>
    </tr>
  `).join('') : `<tr><td colspan="5" style="text-align:center;color:#94a3b8;">No medications prescribed.</td></tr>`;

  const body = `
    ${header({ docType: 'Prescription', docNumber: recordId ? `RX-${recordId}` : null })}

    <h1 class="doc-title"><span class="rx-symbol">℞</span>Prescription</h1>
    <div class="doc-subtitle">For pharmacy dispensing only.</div>

    <div class="panel">
      <h3>Patient</h3>
      <div class="grid-2">
        <div class="field"><div class="label">Name</div><div class="value">${orDash(patient.full_name || patient.name)}</div></div>
        <div class="field"><div class="label">OP Number</div><div class="value">${orDash(patient.outpatient_no || patient.opd)}</div></div>
        <div class="field"><div class="label">Age / Sex</div><div class="value">${orDash(patient.age)} / ${orDash(patient.sex)}</div></div>
        <div class="field"><div class="label">Allergies</div><div class="value">${orDash(patient.allergies)}</div></div>
      </div>
    </div>

    <table class="line-items">
      <thead>
        <tr>
          <th>Medication</th>
          <th>Dosage</th>
          <th>Frequency</th>
          <th>Duration</th>
          <th>Route / Notes</th>
        </tr>
      </thead>
      <tbody>${itemsHtml}</tbody>
    </table>

    ${notes ? `
      <div class="panel" style="margin-top:14px;">
        <h3>Clinical Notes</h3>
        <div>${esc(notes)}</div>
      </div>
    ` : ''}

    <div class="signature-block">
      <div class="line">
        Prescribing Clinician<br/>
        <b>${orDash(doctor?.full_name)}</b><br/>
        Lic: ${orDash(doctor?.license_number)}
      </div>
      <div class="line">Dispensed By (Pharmacy)</div>
    </div>

    ${footer('This prescription is valid for 30 days from the date of issue unless otherwise specified.')}
  `;

  printDocument(`Prescription RX-${recordId || ''}`, body);
};

// =====================================================================
// 3. LAB REPORT
// =====================================================================
export const printLabReport = ({ patient, test, performedBy, orderedBy }) => {
  if (!test) return;

  const body = `
    ${header({ docType: 'Laboratory Report', docNumber: `LAB-${test.test_id ?? ''}` })}

    <h1 class="doc-title">${esc(test.test_name || 'Laboratory Test')}</h1>
    <div class="doc-subtitle">
      Status:
      <span class="badge ${test.status === 'Completed' ? 'paid' : 'pending'}">${orDash(test.status)}</span>
      ${test.priority === 'STAT' ? '<span class="badge stat" style="margin-left:6px;">STAT</span>' : ''}
    </div>

    <div class="panel">
      <h3>Patient</h3>
      <div class="grid-2">
        <div class="field"><div class="label">Name</div><div class="value">${orDash(patient?.full_name || patient?.name)}</div></div>
        <div class="field"><div class="label">OP Number</div><div class="value">${orDash(patient?.outpatient_no || patient?.opd)}</div></div>
        <div class="field"><div class="label">Age / Sex</div><div class="value">${orDash(patient?.age)} / ${orDash(patient?.sex)}</div></div>
        <div class="field"><div class="label">Date of Birth</div><div class="value">${formatDate(patient?.date_of_birth)}</div></div>
      </div>
    </div>

    <div class="panel">
      <h3>Specimen</h3>
      <div class="grid-2">
        <div class="field"><div class="label">Specimen Type</div><div class="value">${orDash(test.specimen_type || test.default_specimen_type)}</div></div>
        <div class="field"><div class="label">Collected</div><div class="value">${formatDate(test.collected_at)}</div></div>
        <div class="field"><div class="label">Ordered By</div><div class="value">${orDash(orderedBy?.full_name || test.ordered_by_name)}</div></div>
        <div class="field"><div class="label">Performed By</div><div class="value">${orDash(performedBy?.full_name || test.performed_by_name)}</div></div>
      </div>
    </div>

    <div class="panel">
      <h3>Results</h3>
      <div style="white-space:pre-wrap;font-family: 'Courier New', monospace; background:#ffffff; padding:10px; border:1px solid #e2e8f0; border-radius:4px;">${orDash(test.result_summary)}</div>
    </div>

    ${test.interpretation ? `
      <div class="panel">
        <h3>Clinical Interpretation</h3>
        <div>${esc(test.interpretation)}</div>
      </div>
    ` : ''}

    <div class="signature-block">
      <div class="line">
        Reported By (Lab Technician)<br/>
        <b>${orDash(performedBy?.full_name || test.performed_by_name)}</b>
      </div>
      <div class="line">Verified By (Pathologist)</div>
    </div>

    ${footer('Critical values are communicated to the requesting clinician within 30 minutes per lab SOP.')}
  `;

  printDocument(`Lab Report LAB-${test.test_id || ''}`, body);
};

// =====================================================================
// 4. PATIENT REGISTRATION CARD
// =====================================================================
export const printPatientCard = (patient) => {
  if (!patient) return;

  const fullName = patient.full_name || `${patient.surname || ''} ${patient.other_names || ''}`.trim();

  const body = `
    ${header({ docType: 'Patient Registration Card', docNumber: patient.outpatient_no || patient.opd })}

    <h1 class="doc-title">${esc(fullName)}</h1>
    <div class="doc-subtitle">${orDash(patient.outpatient_no)} ${patient.inpatient_no ? `· IP: ${esc(patient.inpatient_no)}` : ''}</div>

    <div class="panel">
      <h3>Demographics</h3>
      <div class="grid-2">
        <div class="field"><div class="label">Date of Birth</div><div class="value">${formatDate(patient.date_of_birth)}</div></div>
        <div class="field"><div class="label">Sex</div><div class="value">${orDash(patient.sex)}</div></div>
        <div class="field"><div class="label">Marital Status</div><div class="value">${orDash(patient.marital_status)}</div></div>
        <div class="field"><div class="label">Religion</div><div class="value">${orDash(patient.religion)}</div></div>
        <div class="field"><div class="label">Primary Language</div><div class="value">${orDash(patient.primary_language)}</div></div>
        <div class="field"><div class="label">Nationality</div><div class="value">${orDash(patient.nationality)}</div></div>
      </div>
    </div>

    <div class="panel">
      <h3>Identification & Contact</h3>
      <div class="grid-2">
        <div class="field"><div class="label">ID Type</div><div class="value">${orDash(patient.id_type)}</div></div>
        <div class="field"><div class="label">ID Number</div><div class="value">${orDash(patient.id_number)}</div></div>
        <div class="field"><div class="label">Telephone</div><div class="value">${orDash(patient.telephone_1)}</div></div>
        <div class="field"><div class="label">Alt Telephone</div><div class="value">${orDash(patient.telephone_2)}</div></div>
        <div class="field"><div class="label">Email</div><div class="value">${orDash(patient.email)}</div></div>
        <div class="field"><div class="label">Residence</div><div class="value">${orDash(patient.residence)}, ${orDash(patient.town)}</div></div>
        <div class="field"><div class="label">Occupation</div><div class="value">${orDash(patient.occupation)}</div></div>
        <div class="field"><div class="label">Reference No.</div><div class="value">${orDash(patient.reference_number)}</div></div>
      </div>
    </div>

    <div class="panel">
      <h3>Clinical Snapshot</h3>
      <div class="grid-2">
        <div class="field"><div class="label">Blood Group</div><div class="value">${orDash(patient.blood_group)}</div></div>
        <div class="field"><div class="label">Allergies</div><div class="value">${orDash(patient.allergies)}</div></div>
        <div class="field"><div class="label">Chronic Conditions</div><div class="value">${orDash(patient.chronic_conditions)}</div></div>
      </div>
    </div>

    <div class="panel">
      <h3>Next of Kin</h3>
      <div class="grid-2">
        <div class="field"><div class="label">Name</div><div class="value">${orDash(patient.nok_name)}</div></div>
        <div class="field"><div class="label">Relationship</div><div class="value">${orDash(patient.nok_relationship)}</div></div>
        <div class="field"><div class="label">Contact</div><div class="value">${orDash(patient.nok_contact)}</div></div>
      </div>
    </div>

    ${footer('Confidential — for use by registered hospital staff only.')}
  `;

  printDocument(`Patient ${patient.outpatient_no || ''}`, body);
};

// =====================================================================
// 5. MEDICAL HISTORY SUMMARY
// =====================================================================
export const printMedicalHistory = ({ patient, entries = [], consents = [] }) => {
  if (!patient) return;

  const groupBy = (key) => entries.reduce((acc, e) => {
    const k = e[key] || 'Other';
    acc[k] = acc[k] || [];
    acc[k].push(e);
    return acc;
  }, {});
  const grouped = groupBy('entry_type');

  const sectionsHtml = Object.entries(grouped).map(([type, items]) => `
    <div class="panel">
      <h3>${esc(type.replace(/_/g, ' '))}</h3>
      <ul class="clean">
        ${items.map((e) => `
          <li>
            <b>${esc(e.title)}</b>
            ${e.severity ? ` <span class="badge">${esc(e.severity)}</span>` : ''}
            ${e.status ? ` <span class="badge">${esc(e.status)}</span>` : ''}
            <div style="color:#475569;">${esc(e.description || '')}</div>
            <div style="color:#94a3b8;font-size:10px;">${esc(e.event_date || '')}</div>
          </li>
        `).join('')}
      </ul>
    </div>
  `).join('');

  const consentHtml = consents.length ? `
    <div class="panel">
      <h3>Consent Records</h3>
      <ul class="clean">
        ${consents.map((c) => `
          <li>
            <b>${esc(c.consent_type)}</b> — ${c.consent_given ? 'Given' : 'Withheld'}
            <span style="color:#94a3b8;font-size:10px;"> (${esc(c.consent_method || '')})</span>
            ${c.notes ? `<div style="color:#475569;">${esc(c.notes)}</div>` : ''}
          </li>
        `).join('')}
      </ul>
    </div>
  ` : '';

  const fullName = patient.full_name || `${patient.surname || ''} ${patient.other_names || ''}`.trim();

  const body = `
    ${header({ docType: 'Medical History Summary', docNumber: patient.outpatient_no })}

    <h1 class="doc-title">${esc(fullName)}</h1>
    <div class="doc-subtitle">${orDash(patient.outpatient_no)} · DOB ${formatDate(patient.date_of_birth)} · ${orDash(patient.sex)}</div>

    ${sectionsHtml || '<div class="panel"><i style="color:#94a3b8;">No medical history entries on file.</i></div>'}
    ${consentHtml}

    ${footer('KDPA — Confidential. Patient health information.')}
  `;

  printDocument(`History ${patient.outpatient_no || ''}`, body);
};

// =====================================================================
// 6. ADMISSION / DISCHARGE SLIP
// =====================================================================
export const printAdmissionSlip = ({ patient, admission, doctor }) => {
  if (!patient || !admission) return;
  const isDischarge = admission.status && admission.status.toLowerCase() === 'discharged';
  const docType = isDischarge ? 'Discharge Summary' : 'Admission Slip';

  const body = `
    ${header({ docType, docNumber: `ADM-${admission.admission_id ?? ''}` })}

    <h1 class="doc-title">${esc(docType)}</h1>
    <div class="doc-subtitle">
      <span class="badge ${isDischarge ? 'paid' : 'pending'}">${orDash(admission.status)}</span>
    </div>

    <div class="panel">
      <h3>Patient</h3>
      <div class="grid-2">
        <div class="field"><div class="label">Name</div><div class="value">${orDash(patient.full_name)}</div></div>
        <div class="field"><div class="label">OP / IP No.</div><div class="value">${orDash(patient.outpatient_no)} / ${orDash(patient.inpatient_no)}</div></div>
        <div class="field"><div class="label">Age / Sex</div><div class="value">${orDash(patient.age)} / ${orDash(patient.sex)}</div></div>
        <div class="field"><div class="label">Blood Group</div><div class="value">${orDash(patient.blood_group)}</div></div>
      </div>
    </div>

    <div class="panel">
      <h3>Admission Details</h3>
      <div class="grid-2">
        <div class="field"><div class="label">Ward / Bed</div><div class="value">${orDash(admission.ward_name)} / ${orDash(admission.bed_number)}</div></div>
        <div class="field"><div class="label">Admitted On</div><div class="value">${formatDate(admission.admission_date || admission.created_at)}</div></div>
        <div class="field"><div class="label">Admitting Doctor</div><div class="value">${orDash(doctor?.full_name || admission.doctor_name)}</div></div>
        <div class="field"><div class="label">Diagnosis</div><div class="value">${orDash(admission.primary_diagnosis)}</div></div>
        ${isDischarge ? `<div class="field"><div class="label">Discharged On</div><div class="value">${formatDate(admission.discharge_date)}</div></div>` : ''}
      </div>
    </div>

    ${admission.discharge_summary ? `
      <div class="panel">
        <h3>Discharge Summary</h3>
        <div style="white-space:pre-wrap;">${esc(admission.discharge_summary)}</div>
      </div>
    ` : ''}

    <div class="signature-block">
      <div class="line">Attending Clinician</div>
      <div class="line">Patient / Guardian</div>
    </div>

    ${footer()}
  `;

  printDocument(`${docType} ADM-${admission.admission_id || ''}`, body);
};

// =====================================================================
// 7. RADIOLOGY REPORT
// =====================================================================
export const printRadiologyReport = ({ patient, request, result, radiologist }) => {
  if (!request) return;

  const body = `
    ${header({ docType: 'Radiology Report', docNumber: `RAD-${request.request_id ?? ''}` })}

    <h1 class="doc-title">${esc(request.modality || 'Radiology')} — ${esc(request.body_part || '')}</h1>
    <div class="doc-subtitle">
      <span class="badge ${result ? 'paid' : 'pending'}">${result ? 'Reported' : orDash(request.status)}</span>
    </div>

    <div class="panel">
      <h3>Patient</h3>
      <div class="grid-2">
        <div class="field"><div class="label">Name</div><div class="value">${orDash(patient?.full_name)}</div></div>
        <div class="field"><div class="label">OP Number</div><div class="value">${orDash(patient?.outpatient_no)}</div></div>
        <div class="field"><div class="label">Age / Sex</div><div class="value">${orDash(patient?.age)} / ${orDash(patient?.sex)}</div></div>
        <div class="field"><div class="label">Requested On</div><div class="value">${formatDate(request.created_at)}</div></div>
      </div>
    </div>

    <div class="panel">
      <h3>Clinical Indication</h3>
      <div>${orDash(request.clinical_indication || request.notes)}</div>
    </div>

    ${result ? `
      <div class="panel">
        <h3>Findings</h3>
        <div style="white-space:pre-wrap;">${orDash(result.findings)}</div>
      </div>
      <div class="panel">
        <h3>Impression</h3>
        <div style="white-space:pre-wrap;">${orDash(result.impression)}</div>
      </div>
    ` : '<div class="panel"><i style="color:#94a3b8;">Awaiting radiologist report.</i></div>'}

    <div class="signature-block">
      <div class="line">
        Reporting Radiologist<br/>
        <b>${orDash(radiologist?.full_name || result?.radiologist_name)}</b><br/>
        Lic: ${orDash(radiologist?.license_number)}
      </div>
      <div class="line">Verified</div>
    </div>

    ${footer()}
  `;

  printDocument(`Radiology RAD-${request.request_id || ''}`, body);
};
