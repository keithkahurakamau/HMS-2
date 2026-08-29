import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import AgeingTable from './AgeingTable';

const rows = [
    { tenant_id: 1, tenant_name: 'Mayo Clinic', current: '0.00', b1_30: '15000.00',
      b31_60: '0.00', b61_90: '0.00', b90_plus: '0.00', total: '15000.00', reminders_paused: false },
    { tenant_id: 2, tenant_name: 'MP Shah', current: '49500.00', b1_30: '0.00',
      b31_60: '0.00', b61_90: '0.00', b90_plus: '0.00', total: '49500.00', reminders_paused: true },
];

describe('AgeingTable', () => {
    it('shows one row per hospital with its total', () => {
        render(<AgeingTable rows={rows} onSelect={() => {}} />);
        expect(screen.getByText('Mayo Clinic')).toBeInTheDocument();
        expect(screen.getByText('MP Shah')).toBeInTheDocument();
    });

    it('labels a tenant whose reminders are paused, so a quiet account is not mistaken for a healthy one', () => {
        render(<AgeingTable rows={rows} onSelect={() => {}} />);
        expect(screen.getByText(/reminders paused/i)).toBeInTheDocument();
    });

    it('opens the drawer for the row that was clicked', async () => {
        const onSelect = vi.fn();
        render(<AgeingTable rows={rows} onSelect={onSelect} />);
        screen.getByText('Mayo Clinic').closest('tr').click();
        expect(onSelect).toHaveBeenCalledWith(1);
    });

    it('renders an empty state when nobody owes anything', () => {
        render(<AgeingTable rows={[]} onSelect={() => {}} />);
        expect(screen.getByText(/no outstanding balances/i)).toBeInTheDocument();
    });
});
