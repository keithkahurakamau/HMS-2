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
//
// Tenant letterhead
// -----------------
// A hospital can upload its own pre-designed A4 stationery (Branding Studio →
// Letterhead). When one is active, every document produced here is laid out on
// top of that artwork instead of the generic MediFleet header/footer, so
// invoices, prescriptions, lab reports and the rest all come out on the
// clinic's own paper. `setPrintBranding()` is called by BrandingContext
// whenever branding loads, which keeps this module synchronous — printing must
// stay inside the user's click gesture or the browser blocks the popup.

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
  localStorage.getItem('hms_tenant_name') || 'MediFleet';

/* ── Tenant letterhead ──────────────────────────────────────────────────────
   Held in a module-level cache so printDocument() stays synchronous. */

const A4_WIDTH_MM = 210;
const A4_HEIGHT_MM = 297;

const LETTERHEAD_DEFAULTS = {
  margin_top_mm: 42,
  margin_bottom_mm: 48,
  margin_side_mm: 18,
};

let letterhead = null;
// Text strap-lines configured in Branding Studio; used with or without
// stationery so a tenant can brand its documents without uploading artwork.
let printBranding = { header_text: '', footer_text: '' };

// Same allow-list the app uses for tenant logos: the URL is interpolated into
// an <img src>, and data:image/svg+xml can carry <script>, so SVG is out.
const isSafePrintImage = (url) =>
  typeof url === 'string'
  && url.length > 0
  && url.length <= 5_000_000
  && !/["\\\r\n]/.test(url)
  && (/^data:image\/(png|jpe?g|webp);base64,[A-Za-z0-9+/=]+$/i.test(url)
      || /^https:\/\/[A-Za-z0-9.\-_~:/?#@!$&'*+,;=%]+$/.test(url));

const clampMm = (value, fallback, max) => {
  const n = Number(value);
  if (!Number.isFinite(n) || n < 0 || n > max) return fallback;
  return n;
};

/**
 * Registers the active tenant's print branding. Called by BrandingContext on
 * every branding load; pass null/undefined to fall back to the generic layout.
 */
export const setPrintBranding = (printTemplates) => {
  printBranding = {
    header_text: typeof printTemplates?.header_text === 'string' ? printTemplates.header_text : '',
    footer_text: typeof printTemplates?.footer_text === 'string' ? printTemplates.footer_text : '',
  };
  const cfg = printTemplates?.letterhead;
  if (!cfg?.enabled || !isSafePrintImage(cfg.image)) {
    letterhead = null;
    return;
  }
  const top = clampMm(cfg.margin_top_mm, LETTERHEAD_DEFAULTS.margin_top_mm, 150);
  const bottom = clampMm(cfg.margin_bottom_mm, LETTERHEAD_DEFAULTS.margin_bottom_mm, 150);
  const side = clampMm(cfg.margin_side_mm, LETTERHEAD_DEFAULTS.margin_side_mm, 60);
  // A safe area with no room left would silently print blank pages.
  if (top + bottom >= A4_HEIGHT_MM || side * 2 >= A4_WIDTH_MM) {
    letterhead = null;
    return;
  }
  letterhead = { image: cfg.image, top, bottom, side };
};

/** True when the active tenant prints on its own stationery. */
export const hasLetterhead = () => letterhead !== null;

/* Letterhead layout.

   The artwork has to do two things on a multi-page document: repeat on every
   sheet, and *reserve* the space it occupies so body text never runs beneath
   it. `position: fixed` only does the first — it paints over the flow, and
   `@page` margins with negative offsets proved unreliable in Chromium's print
   pipeline (the artwork drifted into the middle of the page).

   A table with `<thead>` / `<tfoot>` does both: browsers repeat header and
   footer row groups on every printed page *and* reserve their height in the
   flow. That behaviour long predates CSS paged media and is consistent across
   engines, so it is what we rely on.

   Both bands show the *same* stored full-page artwork, cropped with
   `overflow: hidden` — the top band reveals its first `top`mm, the bottom band
   is pulled up so only its last `bottom`mm shows. Cropping in CSS means
   changing a margin re-crops instantly with no re-upload and no canvas work. */
const letterheadStyles = (lh) => `
  /* Full-bleed: the artwork runs to the paper edge, so all spacing is ours. */
  @page { size: A4; margin: 0; }

  html, body { padding: 0; margin: 0; }

  /* Painted artwork — fixed, so Chromium repeats it on every sheet, pinned to
     the physical paper edges (possible because the page margin is 0). */
  .letterhead-band {
    position: fixed;
    left: 0;
    width: ${A4_WIDTH_MM}mm;
    overflow: hidden;
    z-index: 0;
  }
  .letterhead-band img {
    width: 100%;
    height: ${A4_HEIGHT_MM}mm;   /* full sheet; the band crops it */
    object-fit: fill;
    display: block;
  }
  .letterhead-band.top { top: 0; height: ${lh.top}mm; }
  .letterhead-band.bottom { bottom: 0; height: ${lh.bottom}mm; }
  /* Pull the artwork up so the band's window lands on its footer. */
  .letterhead-band.bottom img { margin-top: -${A4_HEIGHT_MM - lh.bottom}mm; }

  /* Reserved space — thead/tfoot repeat on every page AND reserve their
     height in the flow, which fixed positioning alone cannot do. They hold
     empty spacers; the artwork above is what the reader actually sees. */
  .letterhead-doc {
    width: 100%;
    border-collapse: collapse;
    table-layout: fixed;
    position: relative;
    z-index: 1;
  }
  .letterhead-spacer.top { height: ${lh.top}mm; }
  .letterhead-spacer.bottom { height: ${lh.bottom}mm; }

  .letterhead-doc > tbody > tr > td { padding: 0 ${lh.side}mm; vertical-align: top; }
  .letterhead-doc thead td, .letterhead-doc tfoot td { padding: 0; }

  /* The stationery already carries the clinic's identity, so the generic
     brand band collapses to a compact meta line. */
  .doc-header { border-bottom: 1px solid #cbd5e1; padding-bottom: 8px; margin-bottom: 14px; }
  .footer { border-top: 1px solid #e2e8f0; margin-top: 20px; }

  @media print {
    /* Without this Chromium drops the artwork's background colours entirely. */
    body { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  }
`;

const buildDocument = (title, bodyHtml) => {
  const lh = letterhead;
  const styles = lh ? `${SHARED_PRINT_STYLES}\n${letterheadStyles(lh)}` : SHARED_PRINT_STYLES;

  // Two mechanisms, because neither alone is enough: the fixed bands paint the
  // artwork at the paper edges of every sheet, and the thead/tfoot spacers
  // reserve that space in the flow so text never runs underneath it — on the
  // first page, the last page, and every page between.
  const content = lh
    ? `<div class="letterhead-band top" aria-hidden="true"><img src="${lh.image}" alt="" /></div>
<div class="letterhead-band bottom" aria-hidden="true"><img src="${lh.image}" alt="" /></div>
<table class="letterhead-doc">
  <thead><tr><td><div class="letterhead-spacer top"></div></td></tr></thead>
  <tfoot><tr><td><div class="letterhead-spacer bottom"></div></td></tr></tfoot>
  <tbody><tr><td>${bodyHtml}</td></tr></tbody>
</table>`
    : bodyHtml;

  return `
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>${escapeHtml(title)}</title>
  <style>${styles}</style>
</head>
<body>
  ${content}
</body>
</html>
`;
};

// Open a hidden popup, navigate to a blob: URL holding the document, trigger
// print, then revoke the URL. The prior implementation used document.write
// into an about:blank popup, which (a) violates Trusted Types under the
// strict CSP we just shipped and (b) gives the printed page full opener
// access back to the SPA. Loading via a blob URL keeps the popup
// same-origin enough for parent-driven print() while letting us null out
// popup.opener so the printed document can't pivot back into auth state.
export const printDocument = (title, bodyHtml) => {
  const html = buildDocument(title, bodyHtml);
  const blob = new Blob([html], { type: 'text/html;charset=utf-8' });
  const url = URL.createObjectURL(blob);

  const popup = window.open(url, '_blank', 'width=900,height=1100');
  if (popup) {
    try { popup.opener = null; } catch (e) { /* ignore */ }
    const triggerPrint = () => {
      try { popup.focus(); popup.print(); } catch (e) { /* ignore */ }
      const close = () => {
        try { popup.close(); } catch (e) { /* ignore */ }
        URL.revokeObjectURL(url);
      };
      try { popup.onafterprint = close; } catch (e) { /* ignore */ }
      setTimeout(close, 1500);
    };
    popup.onload = triggerPrint;
    return;
  }

  // Fallback: hidden iframe (used when popups are blocked).
  const iframe = document.createElement('iframe');
  iframe.setAttribute('aria-hidden', 'true');
  iframe.style.position = 'fixed';
  iframe.style.right = '0';
  iframe.style.bottom = '0';
  iframe.style.width = '0';
  iframe.style.height = '0';
  iframe.style.border = '0';
  iframe.onload = () => {
    try { iframe.contentWindow.focus(); iframe.contentWindow.print(); } catch (e) { /* ignore */ }
    setTimeout(() => {
      try { document.body.removeChild(iframe); } catch (e) { /* ignore */ }
      URL.revokeObjectURL(url);
    }, 1500);
  };
  iframe.src = url;
  document.body.appendChild(iframe);
};

/**
 * Renders a document against an ad-hoc print-branding config instead of the
 * saved one, then restores the active config. Branding Studio uses this to
 * test-print an *unsaved* letterhead draft. Restore happens synchronously
 * because buildDocument() has already serialised the HTML by then.
 */
export const printDocumentWithBranding = (title, bodyHtml, printTemplates) => {
  const previousLetterhead = letterhead;
  const previousBranding = printBranding;
  try {
    setPrintBranding(printTemplates);
    printDocument(title, bodyHtml);
  } finally {
    letterhead = previousLetterhead;
    printBranding = previousBranding;
  }
};

/** Serialised print HTML — used by tests and the on-screen letterhead preview. */
export const buildPrintHtml = (title, bodyHtml) => buildDocument(title, bodyHtml);

export const printUtils = {
  esc: escapeHtml,
  hospital: getHospitalName,
  // Header reused across templates. On tenant stationery the clinic's identity
  // is already printed above, so the brand band collapses to the document's
  // own identifiers and we don't repeat (or fight with) the artwork.
  header: ({ docType, docNumber, dateLabel = 'Issued' }) => {
    const meta = `
      <div class="meta">
        <strong>${escapeHtml(docType)}</strong>
        ${docNumber ? `<div>No: <b>${escapeHtml(docNumber)}</b></div>` : ''}
        <div>${escapeHtml(dateLabel)}: ${new Date().toLocaleString()}</div>
      </div>
    `;
    if (letterhead) {
      const strap = printBranding.header_text;
      return `
        <div class="doc-header">
          <div>${strap ? `<div class="brand"><small>${escapeHtml(strap)}</small></div>` : ''}</div>
          ${meta}
        </div>
      `;
    }
    return `
      <div class="doc-header">
        <div>
          <div class="brand">
            ${escapeHtml(getHospitalName())}
            <small>${escapeHtml(printBranding.header_text || 'Hospital Management System')}</small>
          </div>
        </div>
        ${meta}
      </div>
    `;
  },
  footer: (extra = '') => {
    const custom = printBranding.footer_text;
    // Stationery carries its own footer artwork; adding the MediFleet
    // provenance line under it would collide with the design.
    const provenance = letterhead
      ? ''
      : `<div>This document was electronically generated by ${escapeHtml(getHospitalName())} via MediFleet.</div>`;
    return `
      <div class="footer">
        ${extra ? `<div>${escapeHtml(extra)}</div>` : ''}
        ${custom ? `<div>${escapeHtml(custom)}</div>` : ''}
        ${provenance}
        <div>Printed on ${new Date().toLocaleString()}.</div>
      </div>
    `;
  },
};
