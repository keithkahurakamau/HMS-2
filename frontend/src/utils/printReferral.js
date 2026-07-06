
// Printable referral letter template — typed | blank-patient | blank.
//
// Split out of printTemplates.js (which was over the 500-line limit) so
// each file stays focused. Same conventions as the other templates: tolerant
// of missing fields, renders ruled lines for hand-filled blanks.

import { printDocument, printUtils } from './printDocument';

const { esc, header, footer } = printUtils;

// n ruled lines for handwriting on paper.
const ruledLines = (n) => Array.from({ length: n }, () =>
  '<div class="ruled-line" style="border-bottom:1px solid #94a3b8;height:24px;"></div>'
).join('');

export const printReferralLetter = ({ mode = 'typed', referral = {}, patient = {}, doctorName = '' }) => {
  const typed = mode === 'typed';
  const withPatient = mode !== 'blank';

  const field = (label, value, blankWidth = '60%') => `
    <div class="field">
      <div class="label">${esc(label)}</div>
      <div class="value">${
        value != null && value !== '' ? esc(value)
              : `<span class="ruled-line" style="display:inline-block;border-bottom:1px solid #94a3b8;width:${blankWidth};height:18px;"></span>`
      }</div>
    </div>`;

  const body = `
    ${header({ docType: 'Referral Letter', docNumber: typed && referral.referral_id ? `REF-${referral.referral_id}` : '—' })}

    <h1 class="doc-title">Referral Letter</h1>
    ${typed ? `<div class="doc-subtitle">Urgency: <span class="badge ${referral.urgency === 'Routine' ? 'paid' : 'pending'}">${esc(referral.urgency || 'Routine')}</span></div>`
            : `<div class="doc-subtitle">Urgency: &nbsp; ☐ Routine &nbsp; ☐ Urgent &nbsp; ☐ Emergency</div>`}

    <div class="panel">
      <h3>Patient</h3>
      <div class="grid-2">
        ${field('Name', withPatient ? patient.patient_name : null)}
        ${field('OP Number', withPatient ? patient.outpatient_no : null)}
        ${field('Age', withPatient ? patient.age : null, '40%')}
        ${field('Sex', withPatient ? patient.gender : null, '40%')}
      </div>
    </div>

    <div class="panel">
      <h3>Referred To</h3>
      <div class="grid-2">
        ${field('Specialty', typed ? referral.specialty : null)}
        ${field('Facility', typed ? referral.target_facility : null)}
        ${field('Clinician', typed ? referral.target_clinician : null)}
      </div>
    </div>

    <div class="panel">
      <h3>Reason for Referral</h3>
      ${typed && referral.reason ? `<p style="white-space:pre-wrap;">${esc(referral.reason)}</p>` : ruledLines(4)}
    </div>

    <div class="panel">
      <h3>Clinical Summary</h3>
      ${typed && referral.clinical_summary ? `<p style="white-space:pre-wrap;">${esc(referral.clinical_summary)}</p>` : ruledLines(6)}
    </div>

    <div class="signature-block">
      <div class="line">${doctorName ? `Referring Doctor: ${esc(doctorName)}` : 'Referring Doctor'}</div>
      <div class="line">Signature &amp; Date</div>
    </div>

    ${footer('Please attend to the referred patient at your earliest convenience.')}
  `;

  printDocument('Referral Letter', body);
};
