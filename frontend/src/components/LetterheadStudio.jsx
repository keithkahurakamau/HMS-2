import React, { useRef, useState } from 'react';
import {
    Upload, Trash2, AlertTriangle, Printer, FileText,
} from 'lucide-react';
import { printDocumentWithBranding, printUtils } from '../utils/printDocument';

/**
 * LetterheadStudio — upload the hospital's own pre-designed A4 stationery and
 * position the safe area that document content flows inside.
 *
 * Hospitals almost always already own this artwork (their designer supplies a
 * full-page letterhead), so the upload takes the page exactly as-is rather than
 * asking an admin to crop separate header and footer bands. At print time the
 * artwork is painted full-bleed on every sheet and the content is inset by the
 * margins configured here — see `printDocument.js` for the paged-media rules.
 *
 * Uploads are downscaled to A4 @ ~150 DPI and re-encoded as JPEG before they
 * leave the browser, which turns a multi-megabyte scan into ~100 KB.
 */

// A4 portrait, in millimetres.
export const A4_W_MM = 210;
export const A4_H_MM = 297;

// 1240 px across 210 mm ≈ 150 DPI — plenty for laser output, small on the wire.
const MAX_WIDTH_PX = 1240;
const JPEG_QUALITY = 0.86;
const MAX_ENCODED_BYTES = 1_100_000;   // stays under the server's 1.2 MB cap
const MAX_SOURCE_BYTES = 25_000_000;   // reject absurd inputs before decoding

export const LETTERHEAD_DEFAULTS = {
    enabled: false,
    image: null,
    margin_top_mm: 42,
    margin_bottom_mm: 48,
    margin_side_mm: 18,
};

/**
 * Downscales an uploaded letterhead to A4 proportions and returns a JPEG data
 * URL. Scans usually carry a slightly-off aspect ratio (paper edges, phone
 * photos), so the image is drawn onto an exact-A4 canvas — the printed sheet is
 * A4 regardless, and normalising here means the on-screen preview matches the
 * paper instead of drifting a few millimetres.
 */
export function compressLetterhead(file) {
    return new Promise((resolve, reject) => {
        if (file.size > MAX_SOURCE_BYTES) {
            reject(new Error('That file is very large. Export the letterhead at a lower resolution and retry.'));
            return;
        }
        const reader = new FileReader();
        reader.onerror = () => reject(new Error('Failed to read the file.'));
        reader.onload = () => {
            const src = reader.result;
            if (typeof src !== 'string' || !src.startsWith('data:image/')) {
                reject(new Error('Unsupported file type. Use a PNG, JPG, or WebP export of your letterhead.'));
                return;
            }
            if (src.startsWith('data:image/svg')) {
                reject(new Error('SVG letterheads are not supported. Export the page as PNG or JPG.'));
                return;
            }
            const img = new Image();
            img.onerror = () => reject(new Error('That image could not be decoded.'));
            img.onload = () => {
                try {
                    const width = Math.min(MAX_WIDTH_PX, Math.max(img.naturalWidth, 600));
                    const height = Math.round((width * A4_H_MM) / A4_W_MM);
                    const canvas = document.createElement('canvas');
                    canvas.width = width;
                    canvas.height = height;
                    const ctx = canvas.getContext('2d');
                    // White ground: a transparent PNG letterhead would otherwise
                    // encode its background as black once flattened into JPEG.
                    ctx.fillStyle = '#ffffff';
                    ctx.fillRect(0, 0, width, height);
                    ctx.drawImage(img, 0, 0, width, height);
                    const out = canvas.toDataURL('image/jpeg', JPEG_QUALITY);
                    if (out.length > MAX_ENCODED_BYTES) {
                        reject(new Error('The letterhead is still too large after compression. Flatten it to a simpler image and retry.'));
                        return;
                    }
                    resolve(out);
                } catch {
                    reject(new Error('Could not process that image.'));
                }
            };
            img.src = src;
        };
        reader.readAsDataURL(file);
    });
}

/** Sample document used by "Print a test page". */
function sampleBody() {
    const { esc } = printUtils;
    return `
    ${printUtils.header({ docType: 'Letterhead test', docNumber: 'TEST-001' })}
    <h1 class="doc-title">Letterhead test page</h1>
    <div class="doc-subtitle">Confirm nothing overlaps your artwork, then print a real document.</div>
    <div class="panel">
      <h3>Patient</h3>
      <div class="grid-2">
        <div class="field"><div class="label">Name</div><div class="value">${esc('Jane Wanjiru Mwangi')}</div></div>
        <div class="field"><div class="label">OP Number</div><div class="value">OP-2026-0001</div></div>
        <div class="field"><div class="label">Date of birth</div><div class="value">14 Mar 1988</div></div>
        <div class="field"><div class="label">Sex</div><div class="value">Female</div></div>
      </div>
    </div>
    <table class="line-items">
      <thead><tr><th>Description</th><th>Category</th><th class="amount">Amount (KES)</th></tr></thead>
      <tbody>
        <tr><td>Consultation</td><td>Clinical</td><td class="amount">2,500.00</td></tr>
        <tr><td>Renal function panel</td><td>Laboratory</td><td class="amount">4,800.00</td></tr>
        <tr><td>Dispensed medication</td><td>Pharmacy</td><td class="amount">1,250.00</td></tr>
      </tbody>
    </table>
    <div class="totals">
      <div class="row"><span>Subtotal</span><span>8,550.00</span></div>
      <div class="row grand"><span>Total</span><span>KES 8,550.00</span></div>
    </div>
    <div class="signature-block">
      <div class="line">Clinician signature</div>
      <div class="line">Patient signature</div>
    </div>
    ${printUtils.footer('This is a test page generated from Branding Studio.')}
  `;
}

export default function LetterheadStudio({ value, onChange, headerText, footerText }) {
    const cfg = { ...LETTERHEAD_DEFAULTS, ...(value || {}) };
    const inputRef = useRef(null);
    const [error, setError] = useState(null);
    const [busy, setBusy] = useState(false);

    const set = (key, v) => onChange({ ...cfg, [key]: v });

    const handleFile = async (file) => {
        if (!file) return;
        setError(null);
        setBusy(true);
        try {
            const dataUrl = await compressLetterhead(file);
            // Uploading artwork is the whole intent, so switch it on for them.
            onChange({ ...cfg, image: dataUrl, enabled: true });
        } catch (e) {
            setError(e.message);
        } finally {
            setBusy(false);
        }
    };

    const handleTestPrint = () => {
        printDocumentWithBranding('Letterhead test page', sampleBody(), {
            header_text: headerText,
            footer_text: footerText,
            letterhead: cfg,
        });
    };

    // Safe area as percentages of the A4 sheet, for the on-screen preview.
    const inset = {
        top: `${(cfg.margin_top_mm / A4_H_MM) * 100}%`,
        bottom: `${(cfg.margin_bottom_mm / A4_H_MM) * 100}%`,
        left: `${(cfg.margin_side_mm / A4_W_MM) * 100}%`,
        right: `${(cfg.margin_side_mm / A4_W_MM) * 100}%`,
    };
    const noRoom = cfg.margin_top_mm + cfg.margin_bottom_mm >= A4_H_MM
        || cfg.margin_side_mm * 2 >= A4_W_MM;
    // Artwork always prints in full now, so a tiny margin no longer hides the
    // letterhead — it makes text land on top of it. Say so before they print.
    const tooTight = cfg.margin_top_mm < 15 || cfg.margin_bottom_mm < 15;

    return (
        <div className="grid gap-5 lg:grid-cols-2">
            {/* ── Controls ── */}
            <div className="space-y-4">
                {!cfg.image ? (
                    <button
                        type="button"
                        onClick={() => inputRef.current?.click()}
                        disabled={busy}
                        className="w-full rounded-2xl border border-dashed border-ink-300 dark:border-ink-700 bg-ink-50/40 dark:bg-ink-800/40 px-5 py-10 flex flex-col items-center text-ink-500 dark:text-ink-400 hover:text-brand-700 hover:border-brand-300 hover:bg-brand-50/30 dark:hover:bg-ink-800/60 transition-colors cursor-pointer disabled:cursor-wait"
                    >
                        <Upload size={22} className="mb-2" />
                        <span className="text-sm font-semibold">
                            {busy ? 'Processing…' : 'Upload your letterhead'}
                        </span>
                        <span className="text-xs mt-1 text-center max-w-xs">
                            A full A4 page — the same artwork your printer or designer supplied. PNG, JPG, or WebP.
                        </span>
                    </button>
                ) : (
                    <div className="flex flex-wrap gap-2">
                        <button
                            type="button"
                            onClick={() => inputRef.current?.click()}
                            disabled={busy}
                            className="btn-secondary cursor-pointer disabled:cursor-wait"
                        >
                            <Upload size={14} /> {busy ? 'Processing…' : 'Replace artwork'}
                        </button>
                        <button
                            type="button"
                            onClick={handleTestPrint}
                            className="btn-secondary cursor-pointer"
                        >
                            <Printer size={14} /> Print a test page
                        </button>
                        <button
                            type="button"
                            onClick={() => onChange({ ...cfg, image: null, enabled: false })}
                            className="btn-danger cursor-pointer"
                        >
                            <Trash2 size={14} /> Remove
                        </button>
                    </div>
                )}
                <input
                    ref={inputRef}
                    aria-label="Upload letterhead image"
                    type="file"
                    accept="image/png,image/jpeg,image/jpg,image/webp"
                    className="hidden"
                    onChange={(e) => { handleFile(e.target.files?.[0]); e.target.value = ''; }}
                />

                {error && (
                    <p className="text-xs text-rose-600 flex items-start gap-1.5">
                        <AlertTriangle size={13} className="shrink-0 mt-0.5" /> {error}
                    </p>
                )}

                {cfg.image && (
                    <>
                        <label className="relative flex items-center gap-3 cursor-pointer select-none">
                            <input
                                type="checkbox"
                                checked={!!cfg.enabled}
                                onChange={(e) => set('enabled', e.target.checked)}
                                className="sr-only peer"
                            />
                            <span className="w-11 h-6 bg-ink-200 dark:bg-ink-700 rounded-full peer peer-checked:bg-brand-500 transition relative after:absolute after:left-0.5 after:top-0.5 after:bg-white after:rounded-full after:w-5 after:h-5 after:transition peer-checked:after:translate-x-5" />
                            <span className="text-sm font-medium text-ink-700 dark:text-ink-200">
                                Print all documents on this letterhead
                            </span>
                        </label>

                        <div className="space-y-3 pt-1">
                            <div className="flex items-center justify-between gap-2">
                                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-500 dark:text-ink-400">
                                    Content safe area
                                </p>
                                <button
                                    type="button"
                                    onClick={() => onChange({
                                        ...cfg,
                                        margin_top_mm: LETTERHEAD_DEFAULTS.margin_top_mm,
                                        margin_bottom_mm: LETTERHEAD_DEFAULTS.margin_bottom_mm,
                                        margin_side_mm: LETTERHEAD_DEFAULTS.margin_side_mm,
                                    })}
                                    className="text-xs font-semibold text-brand-600 hover:text-brand-700 cursor-pointer"
                                >
                                    Reset to recommended
                                </button>
                            </div>
                            <MmSlider label="Top margin" hint="Clear of your header artwork"
                                value={cfg.margin_top_mm} min={0} max={120}
                                onChange={(v) => set('margin_top_mm', v)} />
                            <MmSlider label="Bottom margin" hint="Clear of your footer artwork"
                                value={cfg.margin_bottom_mm} min={0} max={120}
                                onChange={(v) => set('margin_bottom_mm', v)} />
                            <MmSlider label="Side margins" hint="Left and right"
                                value={cfg.margin_side_mm} min={0} max={50}
                                onChange={(v) => set('margin_side_mm', v)} />
                        </div>


                        {!noRoom && tooTight && (
                            <p className="text-xs text-amber-600 dark:text-amber-400 flex items-start gap-1.5">
                                <AlertTriangle size={13} className="shrink-0 mt-0.5" />
                                These margins are very tight — document text will print over your
                                header or footer artwork. Most letterheads need roughly 40 mm top
                                and 45 mm bottom.
                            </p>
                        )}

                        {noRoom && (
                            <p className="text-xs text-rose-600 flex items-start gap-1.5">
                                <AlertTriangle size={13} className="shrink-0 mt-0.5" />
                                These margins leave no printable area. Reduce them before saving.
                            </p>
                        )}
                    </>
                )}
            </div>

            {/* ── A4 preview ── */}
            <div>
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-500 dark:text-ink-400 mb-2">
                    A4 preview
                </p>
                <div
                    className="relative mx-auto w-full max-w-[320px] bg-white rounded-lg overflow-hidden ring-1 ring-ink-200 dark:ring-ink-700 shadow-soft"
                    style={{ aspectRatio: `${A4_W_MM} / ${A4_H_MM}` }}
                >
                    {cfg.image ? (
                        <img src={cfg.image} alt="Letterhead preview"
                            className="absolute inset-0 w-full h-full object-fill" />
                    ) : (
                        <div className="absolute inset-0 flex flex-col items-center justify-center text-ink-300 dark:text-ink-600">
                            <FileText size={30} />
                            <span className="text-xs mt-2">No letterhead uploaded</span>
                        </div>
                    )}
                    {cfg.image && !noRoom && (
                        <div
                            className="absolute border-2 border-dashed border-brand-500/70 bg-brand-500/5"
                            style={inset}
                        >
                            <div className="p-1.5 space-y-1">
                                <div className="h-1.5 w-2/3 rounded-full bg-brand-500/35" />
                                <div className="h-1 w-full rounded-full bg-ink-300/60" />
                                <div className="h-1 w-full rounded-full bg-ink-300/60" />
                                <div className="h-1 w-4/5 rounded-full bg-ink-300/60" />
                            </div>
                        </div>
                    )}
                </div>
                <p className="mt-2 text-center text-2xs text-ink-500 dark:text-ink-400">
                    The dashed box is where document content prints.
                </p>
            </div>
        </div>
    );
}

function MmSlider({ label, hint, value, min, max, onChange }) {
    const id = `lh-${label.toLowerCase().replace(/[^a-z]+/g, '-')}`;
    return (
        <div>
            <div className="flex items-baseline justify-between">
                <label htmlFor={id} className="text-sm font-medium text-ink-700 dark:text-ink-200">{label}</label>
                <span className="text-xs font-mono text-ink-500 dark:text-ink-400 tabular-nums">{value} mm</span>
            </div>
            <input
                id={id}
                type="range"
                min={min}
                max={max}
                step={1}
                value={value}
                onChange={(e) => onChange(Number(e.target.value))}
                className="w-full accent-brand-600 cursor-pointer"
            />
            <p className="text-2xs text-ink-500 dark:text-ink-400">{hint}</p>
        </div>
    );
}
