import React from 'react';
import { describe, it, expect } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithProviders } from '../test/renderWithProviders';
import PublicFooter, { PARENT_COMPANY } from './PublicFooter';

describe('PublicFooter', () => {
    it('attributes MediFleet to its parent company, and links to it', () => {
        renderWithProviders(<PublicFooter />);
        expect(screen.getByText(/A product of/i)).toBeInTheDocument();
        const link = screen.getByRole('link', { name: PARENT_COMPANY });
        expect(link).toHaveAttribute('href', 'https://www.novahabitat.tech');
        // External target needs noopener, or the new tab can reach window.opener.
        expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'));
    });

    it('still carries the MediFleet copyright line', () => {
        renderWithProviders(<PublicFooter />);
        const year = new Date().getFullYear();
        expect(screen.getByText(new RegExp(`${year}\\s+MediFleet`))).toBeInTheDocument();
    });

    it('renders each page its own quick links', () => {
        renderWithProviders(
            <PublicFooter>
                <a href="/demo">Demo</a>
            </PublicFooter>,
        );
        expect(screen.getByRole('link', { name: 'Demo' })).toBeInTheDocument();
    });
});
