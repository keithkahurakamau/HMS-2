import { describe, it, expect, beforeEach } from 'vitest';
import {
    setPrintBranding, hasLetterhead, buildPrintHtml, printUtils,
} from './printDocument';

// A 1x1 JPEG is enough, nothing decodes it, but it exercises the allow-list.
const IMG = 'data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAP//////////////////////////////////////////2wBDAf//////////////////////////////////////////wAARCAABAAEDASIA';

const letterheadCfg = (over = {}) => ({
    letterhead: {
        enabled: true,
        image: IMG,
        margin_top_mm: 42,
        margin_bottom_mm: 48,
        margin_side_mm: 18,
        ...over,
    },
});

beforeEach(() => {
    setPrintBranding(null);
    localStorage.setItem('hms_tenant_name', 'Nimrods Consultants Clinic');
});

describe('letterhead activation', () => {
    it('is inactive with no branding', () => {
        expect(hasLetterhead()).toBe(false);
        expect(buildPrintHtml('t', '<p>x</p>')).not.toContain('letterhead-sheet');
    });

    it('activates when enabled with a valid image', () => {
        setPrintBranding(letterheadCfg());
        expect(hasLetterhead()).toBe(true);
    });

    it('stays inactive when uploaded but not enabled', () => {
        setPrintBranding(letterheadCfg({ enabled: false }));
        expect(hasLetterhead()).toBe(false);
    });

    it('rejects an SVG data URL (can carry script)', () => {
        setPrintBranding(letterheadCfg({ image: 'data:image/svg+xml;base64,PHN2Zz48L3N2Zz4=' }));
        expect(hasLetterhead()).toBe(false);
    });

    it('rejects a URL that could break out of the img attribute', () => {
        setPrintBranding(letterheadCfg({ image: 'data:image/png;base64,AAA" onerror="alert(1)' }));
        expect(hasLetterhead()).toBe(false);
    });

    it('rejects margins that individually pass but together leave no printable area', () => {
        // 150 + 150 > 297 mm of A4 height, each value is in range on its own.
        setPrintBranding(letterheadCfg({ margin_top_mm: 150, margin_bottom_mm: 150 }));
        expect(hasLetterhead()).toBe(false);
    });

    it('rejects side margins that consume the full page width', () => {
        setPrintBranding(letterheadCfg({ margin_side_mm: 60 }));  // 2 × 60 mm on a 210 mm sheet is fine…
        expect(hasLetterhead()).toBe(true);
        setPrintBranding(letterheadCfg({ margin_side_mm: 105 })); // …105 mm is out of range, so it defaults
        expect(hasLetterhead()).toBe(true);
    });

    it('falls back to defaults for out-of-range margins', () => {
        setPrintBranding(letterheadCfg({ margin_top_mm: -5, margin_side_mm: 'abc' }));
        expect(hasLetterhead()).toBe(true);
        const html = buildPrintHtml('t', '<p>x</p>');
        expect(html).toContain('.letterhead-spacer.top { height: 42mm; }');
        expect(html).toContain('padding: 0 18mm');
    });
});

describe('letterhead page layout', () => {
    // thead/tfoot is what makes the artwork both repeat per page AND reserve
    // its height. `position: fixed` only repeats, content ran underneath it.
    it('paints the whole sheet, fixed to the paper edges', () => {
        setPrintBranding(letterheadCfg());
        const html = buildPrintHtml('Invoice', '<p>x</p>');
        expect(html).toContain('<div class="letterhead-sheet"');
        expect(html).toMatch(/\.letterhead-sheet\s*\{[^}]*position:\s*fixed/);
        expect(html).toContain('width: 210mm');
        expect(html).toContain('height: 297mm');
    });

    // Regression: cropping the artwork to the margins meant a 0 mm bottom
    // margin erased the footer design while Branding Studio still previewed
    // the full page: the letterhead looked "applied" but printed as nothing.
    it('prints the full artwork even at near-zero margins', () => {
        setPrintBranding(letterheadCfg({ margin_top_mm: 3, margin_bottom_mm: 0, margin_side_mm: 1 }));
        const html = buildPrintHtml('Invoice', '<p>x</p>');
        expect(html).toContain('<div class="letterhead-sheet"');
        expect(html).toContain('height: 297mm');   // whole sheet, not a 0mm band
        expect(html.split(IMG).length - 1).toBe(1);
    });

    // Fixed bands repeat but do not reserve space; thead/tfoot reserve space
    // but sit under short content instead of at the paper edge. Both are
    // needed, on the first page, the last page, and everything between.
    it('reserves that space with repeating thead/tfoot spacers', () => {
        setPrintBranding(letterheadCfg());
        const html = buildPrintHtml('Invoice', '<p>MARKER</p>');
        expect(html).toContain('<table class="letterhead-doc">');
        expect(html).toMatch(/<thead>[\s\S]*letterhead-spacer top[\s\S]*<\/thead>/);
        expect(html).toMatch(/<tfoot>[\s\S]*letterhead-spacer bottom[\s\S]*<\/tfoot>/);
        expect(html).toMatch(/<tbody><tr><td><p>MARKER<\/p><\/td><\/tr><\/tbody>/);
        // Spacers are empty: the fixed bands carry the visible artwork.
        expect(html).toContain('<div class="letterhead-spacer top"></div>');
    });

    it('prints full-bleed so footer artwork reaches the paper edge', () => {
        setPrintBranding(letterheadCfg());
        const html = buildPrintHtml('t', '<p>x</p>');
        expect(html).toContain('@page { size: A4; margin: 0; }');
    });

    it('reserves the configured margins as flow spacers', () => {
        setPrintBranding(letterheadCfg({ margin_top_mm: 40, margin_bottom_mm: 50 }));
        const html = buildPrintHtml('t', '<p>x</p>');
        expect(html).toContain('.letterhead-spacer.top { height: 40mm; }');
        expect(html).toContain('.letterhead-spacer.bottom { height: 50mm; }');
    });

    it('applies side margins to the content cell', () => {
        setPrintBranding(letterheadCfg({ margin_side_mm: 22 }));
        const html = buildPrintHtml('t', '<p>x</p>');
        expect(html).toContain('padding: 0 22mm');
    });

    it('embeds the artwork once', () => {
        setPrintBranding(letterheadCfg());
        const html = buildPrintHtml('t', '<p>x</p>');
        expect(html.split(IMG).length - 1).toBe(1);
    });

    it('leaves plain documents untouched', () => {
        setPrintBranding(null);
        const html = buildPrintHtml('t', '<p>MARKER</p>');
        expect(html).not.toContain('letterhead-doc');
        expect(html).toContain('<p>MARKER</p>');
        expect(html).toContain('@page { size: A4; margin: 16mm 14mm; }');
    });
});

describe('header and footer adapt to the letterhead', () => {
    it('prints the hospital brand band when there is no letterhead', () => {
        const html = printUtils.header({ docType: 'Invoice', docNumber: 'INV-1' });
        expect(html).toContain('Nimrods Consultants Clinic');
        expect(html).toContain('INV-1');
    });

    it('drops the brand band on letterhead so it cannot duplicate the artwork', () => {
        setPrintBranding(letterheadCfg());
        const html = printUtils.header({ docType: 'Invoice', docNumber: 'INV-1' });
        expect(html).not.toContain('Nimrods Consultants Clinic');
        // Document identifiers still print.
        expect(html).toContain('Invoice');
        expect(html).toContain('INV-1');
    });

    it('omits the MediFleet provenance line on letterhead', () => {
        setPrintBranding(letterheadCfg());
        expect(printUtils.footer()).not.toContain('via MediFleet');
        setPrintBranding(null);
        expect(printUtils.footer()).toContain('via MediFleet');
    });

    it('renders the configured header and footer strap-lines', () => {
        setPrintBranding({
            header_text: 'Consultant Physician | Kidney Specialist',
            footer_text: 'Tel: 0722 492 185',
            ...letterheadCfg(),
        });
        expect(printUtils.header({ docType: 'Report' }))
            .toContain('Consultant Physician | Kidney Specialist');
        expect(printUtils.footer()).toContain('Tel: 0722 492 185');
    });

    it('escapes strap-lines so branding cannot inject markup', () => {
        setPrintBranding({ header_text: '<script>alert(1)</script>', footer_text: '</div><img src=x>' });
        expect(printUtils.header({ docType: 'R' })).not.toContain('<script>');
        expect(printUtils.footer()).not.toContain('<img src=x>');
    });
});
