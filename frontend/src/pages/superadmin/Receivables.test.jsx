import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../../api/receivables', async () => {
    const actual = await vi.importActual('../../api/receivables');
    return {
        ...actual,
        getSummary: vi.fn(),
        getAgeing: vi.fn(),
        runBillingNow: vi.fn(),
        getTenantDetail: vi.fn(),
    };
});

vi.mock('react-hot-toast', () => ({
    default: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }),
}));

import { getSummary, getAgeing, runBillingNow } from '../../api/receivables';
import toast from 'react-hot-toast';
import Receivables from './Receivables';

const summary = { billed: '67500.00', received: '18500.00', outstanding: '49000.00', overdue: '15000.00' };
const rows = [
    { tenant_id: 1, tenant_name: 'Mayo Clinic', current: '0.00', b1_30: '15000.00',
      b31_60: '0.00', b61_90: '0.00', b90_plus: '0.00', total: '15000.00', reminders_paused: false },
];

describe('Receivables page', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        getSummary.mockResolvedValue(summary);
        getAgeing.mockResolvedValue(rows);
    });

    it('shows the four summary totals and the ageing table once loaded', async () => {
        render(<Receivables />);
        expect(await screen.findByText('Mayo Clinic')).toBeInTheDocument();
        expect(screen.getByText('KES 67,500.00')).toBeInTheDocument();
        expect(screen.getByText('KES 18,500.00')).toBeInTheDocument();
        expect(screen.getByText('KES 49,000.00')).toBeInTheDocument();
        // "KES 15,000.00" appears twice: the Overdue stat tile, and the
        // ageing table's 1-30 day bucket for Mayo Clinic. Both are correct.
        expect(screen.getAllByText('KES 15,000.00').length).toBeGreaterThanOrEqual(2);
    });

    it('shows an error state when the ledger fails to load', async () => {
        getSummary.mockRejectedValue({ response: { data: { detail: 'Ledger unavailable.' } } });
        render(<Receivables />);
        expect(await screen.findByText('Ledger unavailable.')).toBeInTheDocument();
    });

    it('treats a SKIPPED billing run as informational, never as a failure', async () => {
        const user = userEvent.setup();
        runBillingNow.mockResolvedValue({
            ok: true, skipped: true, invoices_created: 0, reminders_sent: 0, failures: [],
            message: 'Billing run already in progress, skipped.',
        });
        render(<Receivables />);
        await screen.findByText('Mayo Clinic');

        await user.click(screen.getByRole('button', { name: /run billing now/i }));

        await waitFor(() => expect(runBillingNow).toHaveBeenCalled());
        expect(toast.error).not.toHaveBeenCalled();
        expect(toast).toHaveBeenCalledWith('Billing run already in progress, skipped.');
    });

    it('reports a genuine billing failure as an error', async () => {
        const user = userEvent.setup();
        runBillingNow.mockResolvedValue({
            ok: false, skipped: false, invoices_created: 1, reminders_sent: 0,
            failures: ['tenant 3: could not raise invoice'],
            message: 'Billing run completed with 1 failure(s).',
        });
        render(<Receivables />);
        await screen.findByText('Mayo Clinic');

        await user.click(screen.getByRole('button', { name: /run billing now/i }));

        await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Billing run completed with 1 failure(s).'));
    });
});
