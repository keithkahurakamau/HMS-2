import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../utils/printDocument', () => ({
    printDocumentWithBranding: vi.fn(),
    printUtils: {
        esc: (v) => String(v ?? ''),
        header: () => '<div class="doc-header"></div>',
        footer: () => '<div class="footer"></div>',
    },
}));

import LetterheadStudio, { LETTERHEAD_DEFAULTS } from './LetterheadStudio';
import { printDocumentWithBranding } from '../utils/printDocument';

const IMG = 'data:image/jpeg;base64,AAAA';
const withArt = { ...LETTERHEAD_DEFAULTS, enabled: true, image: IMG };

beforeEach(() => vi.clearAllMocks());

describe('empty state', () => {
    it('invites an upload and hides the margin controls', () => {
        render(<LetterheadStudio value={LETTERHEAD_DEFAULTS} onChange={vi.fn()} />);
        expect(screen.getByText(/Upload your letterhead/i)).toBeInTheDocument();
        expect(screen.getByText(/No letterhead uploaded/i)).toBeInTheDocument();
        expect(screen.queryByLabelText(/Top margin/i)).not.toBeInTheDocument();
    });
});

describe('with artwork', () => {
    it('shows the artwork, the safe-area sliders, and the test-print action', () => {
        render(<LetterheadStudio value={withArt} onChange={vi.fn()} />);
        expect(screen.getByAltText('Letterhead preview')).toHaveAttribute('src', IMG);
        expect(screen.getByLabelText(/Top margin/i)).toHaveValue('42');
        expect(screen.getByLabelText(/Bottom margin/i)).toHaveValue('48');
        expect(screen.getByLabelText(/Side margins/i)).toHaveValue('18');
        expect(screen.getByRole('button', { name: /Print a test page/i })).toBeInTheDocument();
    });

    it('reports margin changes to the parent as numbers', () => {
        const onChange = vi.fn();
        render(<LetterheadStudio value={withArt} onChange={onChange} />);
        // jsdom range inputs ignore arrow keys, so drive the change directly.
        fireEvent.change(screen.getByLabelText(/Top margin/i), { target: { value: '55' } });
        // Number, not "55", the print CSS interpolates this into mm values.
        expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ margin_top_mm: 55 }));
    });

    it('toggling off keeps the artwork so it can be switched back on', async () => {
        const onChange = vi.fn();
        render(<LetterheadStudio value={withArt} onChange={onChange} />);
        await userEvent.click(screen.getByLabelText(/Print all documents on this letterhead/i));
        expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ enabled: false, image: IMG }));
    });

    it('removing clears the artwork and disables letterhead printing', async () => {
        const onChange = vi.fn();
        render(<LetterheadStudio value={withArt} onChange={onChange} />);
        await userEvent.click(screen.getByRole('button', { name: /Remove/i }));
        expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ image: null, enabled: false }));
    });

    it('test-prints against the unsaved draft, not the saved config', async () => {
        const draft = { ...withArt, margin_top_mm: 55 };
        render(<LetterheadStudio value={draft} onChange={vi.fn()}
            headerText="Kidney Specialist" footerText="Tel 0722" />);
        await userEvent.click(screen.getByRole('button', { name: /Print a test page/i }));
        expect(printDocumentWithBranding).toHaveBeenCalledWith(
            expect.any(String),
            expect.any(String),
            expect.objectContaining({
                header_text: 'Kidney Specialist',
                footer_text: 'Tel 0722',
                letterhead: expect.objectContaining({ margin_top_mm: 55 }),
            }),
        );
    });

    it('warns that tight margins will print text over the artwork', () => {
        // The artwork always prints in full now, so a small margin no longer
        // hides the letterhead: it makes content land on top of it.
        render(<LetterheadStudio value={{ ...withArt, margin_top_mm: 3, margin_bottom_mm: 0 }}
            onChange={vi.fn()} />);
        expect(screen.getByText(/print over your\s+header or footer artwork/i)).toBeInTheDocument();
    });

    it('offers a one-click reset back to the recommended safe area', async () => {
        const onChange = vi.fn();
        render(<LetterheadStudio value={{ ...withArt, margin_top_mm: 3, margin_bottom_mm: 0, margin_side_mm: 1 }}
            onChange={onChange} />);
        await userEvent.click(screen.getByRole('button', { name: /Reset to recommended/i }));
        expect(onChange).toHaveBeenCalledWith(expect.objectContaining({
            margin_top_mm: 42, margin_bottom_mm: 48, margin_side_mm: 18,
        }));
    });

    it('warns instead of previewing when margins leave no printable area', () => {
        render(<LetterheadStudio value={{ ...withArt, margin_top_mm: 150, margin_bottom_mm: 150 }}
            onChange={vi.fn()} />);
        expect(screen.getByText(/leave no printable area/i)).toBeInTheDocument();
    });
});
