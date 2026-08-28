import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { Skeleton, SkeletonTable } from './Skeleton';

describe('Skeleton', () => {
    it('is hidden from assistive technology', () => {
        render(<Skeleton className="h-4 w-24" />);
        expect(screen.getByTestId('skeleton')).toHaveAttribute('aria-hidden', 'true');
    });

    it('keeps any className it is given alongside the skeleton class', () => {
        render(<Skeleton className="h-4 w-24" />);
        const node = screen.getByTestId('skeleton');
        expect(node).toHaveClass('skeleton');
        expect(node).toHaveClass('h-4');
    });
});

describe('SkeletonTable', () => {
    it('renders the requested grid of cells', () => {
        render(<SkeletonTable rows={3} cols={4} />);
        expect(screen.getAllByTestId('skeleton')).toHaveLength(12);
    });

    it('announces loading once for screen readers', () => {
        render(<SkeletonTable rows={2} cols={2} />);
        expect(screen.getByRole('status')).toHaveTextContent(/loading/i);
    });

    it('defaults to a sensible grid when given no dimensions', () => {
        render(<SkeletonTable />);
        expect(screen.getAllByTestId('skeleton').length).toBeGreaterThan(0);
    });
});
