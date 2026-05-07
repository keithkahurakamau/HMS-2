// Centralized print utility.
//
// Each module passes (a) a document title and (b) an HTML body fragment from one
// of the templates in `printTemplates.js`. We open a hidden popup, write a
// self-contained HTML doc with the shared print stylesheet, wait for it to
// render, fire window.print(), and close on completion or cancel.
//
// Self-containing the HTML means the live app's CSS can never bleed into the
// printed output — every document looks the same regardless of which page
// triggered it.

const SHARED_PRINT_STYLES = `
  @page { size: A4; margin: 16mm 14mm; }

  * { box-sizing: border-box; }

  body {
    font-family: 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
    color: #0f172a;
    margin: 0;
    padding: 24px;
    background: #ffffff;
    font-size: 12px;
    line-height: 1.45;
  }

  .doc-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    border-bottom: 2px solid #0f172a;
    padding-bottom: 12px;
    margin-bottom: 18px;
  }

  .doc-header .brand {
    font-size: 20px;
    font-weight: 800;
    letter-spacing: -0.01em;
    color: #0f172a;
  }

  .doc-header .brand small {
    display: block;
    font-size: 10px;
    font-weight: 500;
    color: #64748b;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin-top: 2px;
  }

  .doc-header .meta {
    text-align: right;
    font-size: 11px;
    color: #475569;
  }

  .doc-header .meta strong {
    display: block;
    color: #0f172a;
    font-size: 13px;
  }

  h1.doc-title {
    font-size: 22px;
    font-weight: 800;
    margin: 0 0 4px 0;
    color: #0f172a;
    letter-spacing: -0.01em;
  }

  .doc-subtitle {
    font-size: 12px;
    color: #64748b;
    margin-bottom: 18px;
  }

  .panel {
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    padding: 12px 14px;
    margin-bottom: 14px;
    background: #f8fafc;
  }

  .panel h3 {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #475569;
    margin: 0 0 8px 0;
    font-weight: 700;
  }

  .grid-2 {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 6px 24px;
  }

  .grid-3 {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 6px 24px;
  }

  .field { display: flex; gap: 6px; padding: 2px 0; }
  .field .label {
    color: #64748b;
    font-weight: 600;
    min-width: 110px;
  }
  .field .value {
    color: #0f172a;
    font-weight: 500;
  }

  table.line-items {
    width: 100%;
    border-collapse: collapse;
    margin-top: 6px;
  }

  table.line-items th {
    text-align: left;
    background: #0f172a;
    color: #ffffff;
    padding: 8px 10px;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-weight: 700;
  }

  table.line-items td {
    padding: 8px 10px;
    border-bottom: 1px solid #e2e8f0;
    font-size: 12px;
  }

  table.line-items tr:last-child td { border-bottom: none; }

  table.line-items td.amount,
  table.line-items th.amount { text-align: right; font-variant-numeric: tabular-nums; }

  .totals {
    margin-top: 10px;
    margin-left: auto;
    width: 50%;
    border-top: 1px solid #cbd5e1;
    padding-top: 8px;
  }

  .totals .row {
    display: flex;
    justify-content: space-between;
    padding: 4px 10px;
    font-size: 12px;
  }

  .totals .row.grand {
    font-size: 14px;
    font-weight: 800;
    background: #0f172a;
    color: #ffffff;
    padding: 8px 10px;
    border-radius: 4px;
    margin-top: 4px;
  }

  .signature-block {
    margin-top: 36px;
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 36px;
  }

  .signature-block .line {
    border-top: 1px solid #0f172a;
    padding-top: 4px;
    font-size: 11px;
    color: #475569;
  }

  .footer {
    margin-top: 28px;
    padding-top: 10px;
    border-top: 1px solid #e2e8f0;
    text-align: center;
    font-size: 10px;
    color: #94a3b8;
  }

  .badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 999px;
    background: #e2e8f0;
    color: #0f172a;
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  .badge.paid { background: #dcfce7; color: #166534; }
  .badge.pending { background: #fef3c7; color: #92400e; }
  .badge.urgent, .badge.stat { background: #fee2e2; color: #991b1b; }

  .rx-symbol {
    font-family: 'Times New Roman', serif;
    font-size: 28px;
    font-weight: 800;
    color: #0f172a;
    margin-right: 10px;
    vertical-align: middle;
  }

  ul.clean { padding-left: 18px; margin: 4px 0; }
  ul.clean li { margin: 2px 0; }

  .page-break { page-break-after: always; }

  @media print {
    body { padding: 0; }
    .no-print { display: none !important; }
  }
`;

const escapeHtml = (value) => {
  if (value === null || value === undefined) return '';
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
};

const getHospitalName = () =>
  localStorage.getItem('hms_tenant_name') || 'HMS Enterprise';

const buildDocument = (title, bodyHtml) => `
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>${escapeHtml(title)}</title>
  <style>${SHARED_PRINT_STYLES}</style>
</head>
<body>
  ${bodyHtml}
</body>
</html>
`;

// Open a hidden popup, write the document, trigger print, close on completion.
// If popups are blocked, we fall back to an inline iframe.
export const printDocument = (title, bodyHtml) => {
  const html = buildDocument(title, bodyHtml);

  const popup = window.open('', '_blank', 'width=900,height=1100');
  if (popup) {
    popup.document.open();
    popup.document.write(html);
    popup.document.close();

    const triggerPrint = () => {
      popup.focus();
      popup.print();
      // Close shortly after the print dialog resolves. Some browsers fire
      // afterprint synchronously when cancelled, others asynchronously.
      const close = () => { try { popup.close(); } catch (e) {} };
      popup.onafterprint = close;
      setTimeout(close, 500);
    };

    if (popup.document.readyState === 'complete') {
      triggerPrint();
    } else {
      popup.onload = triggerPrint;
    }
    return;
  }

  // Fallback: hidden iframe (used when popups are blocked).
  const iframe = document.createElement('iframe');
  iframe.style.position = 'fixed';
  iframe.style.right = '0';
  iframe.style.bottom = '0';
  iframe.style.width = '0';
  iframe.style.height = '0';
  iframe.style.border = '0';
  document.body.appendChild(iframe);

  const doc = iframe.contentWindow.document;
  doc.open();
  doc.write(html);
  doc.close();

  iframe.onload = () => {
    iframe.contentWindow.focus();
    iframe.contentWindow.print();
    setTimeout(() => document.body.removeChild(iframe), 1000);
  };
};

export const printUtils = {
  esc: escapeHtml,
  hospital: getHospitalName,
  // Header reused across templates.
  header: ({ docType, docNumber, dateLabel = 'Issued' }) => `
    <div class="doc-header">
      <div>
        <div class="brand">
          ${escapeHtml(getHospitalName())}
          <small>Hospital Management System</small>
        </div>
      </div>
      <div class="meta">
        <strong>${escapeHtml(docType)}</strong>
        ${docNumber ? `<div>No: <b>${escapeHtml(docNumber)}</b></div>` : ''}
        <div>${escapeHtml(dateLabel)}: ${new Date().toLocaleString()}</div>
      </div>
    </div>
  `,
  footer: (extra = '') => `
    <div class="footer">
      ${extra ? `<div>${escapeHtml(extra)}</div>` : ''}
      <div>This document was electronically generated by ${escapeHtml(getHospitalName())} HMS.</div>
      <div>Printed on ${new Date().toLocaleString()}.</div>
    </div>
  `,
};
