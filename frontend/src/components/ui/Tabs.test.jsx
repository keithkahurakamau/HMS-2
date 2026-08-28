import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import Tabs from './Tabs';

const items = [
    { id: 'orders', label: 'Orders' },
    { id: 'results', label: 'Results', count: 3 },
    { id: 'history', label: 'History' },
];

describe('Tabs', () => {
    it('exposes a tablist with one tab per item', () => {
        render(<Tabs items={items} activeId="orders" onChange={() => {}} />);
        expect(screen.getByRole('tablist')).toBeInTheDocument();
        expect(screen.getAllByRole('tab')).toHaveLength(3);
    });

    it('marks only the active tab as selected', () => {
        render(<Tabs items={items} activeId="orders" onChange={() => {}} />);
        expect(screen.getByRole('tab', { name: /orders/i })).toHaveAttribute('aria-selected', 'true');
        expect(screen.getByRole('tab', { name: /results/i })).toHaveAttribute('aria-selected', 'false');
    });

    it('reports the clicked tab', async () => {
        const onChange = vi.fn();
        render(<Tabs items={items} activeId="orders" onChange={onChange} />);
        await userEvent.click(screen.getByRole('tab', { name: /results/i }));
        expect(onChange).toHaveBeenCalledWith('results');
    });

    it('moves to the next tab with the right arrow key', async () => {
        const onChange = vi.fn();
        render(<Tabs items={items} activeId="orders" onChange={onChange} />);
        screen.getByRole('tab', { name: /orders/i }).focus();
        await userEvent.keyboard('{ArrowRight}');
        expect(onChange).toHaveBeenCalledWith('results');
    });

    it('wraps around to the last tab with the left arrow key', async () => {
        const onChange = vi.fn();
        render(<Tabs items={items} activeId="orders" onChange={onChange} />);
        screen.getByRole('tab', { name: /orders/i }).focus();
        await userEvent.keyboard('{ArrowLeft}');
        expect(onChange).toHaveBeenCalledWith('history');
    });

    it('keeps only the active tab in the tab order', () => {
        render(<Tabs items={items} activeId="results" onChange={() => {}} />);
        expect(screen.getByRole('tab', { name: /results/i })).toHaveAttribute('tabindex', '0');
        expect(screen.getByRole('tab', { name: /orders/i })).toHaveAttribute('tabindex', '-1');
    });

    it('renders a count when one is given', () => {
        render(<Tabs items={items} activeId="orders" onChange={() => {}} />);
        expect(screen.getByRole('tab', { name: /results/i })).toHaveTextContent('3');
    });
});
