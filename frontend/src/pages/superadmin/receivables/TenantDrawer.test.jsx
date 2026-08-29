import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../../../api/receivables', async () => {
    const actual = await vi.importActual('../../../api/receivables');
    return {
        ...actual,
        getTenantDetail: vi.fn(),
        recordPayment: vi.fn(),
        voidInvoice: vi.fn(),
        setReminders: vi.fn(),
        updateSubscription: vi.fn(),
    };
});

vi.mock('react-hot-toast', () => ({
    default: { success: vi.fn(), error: vi.fn() },
}));

import {
    getTenantDetail, recordPayment, setReminders,
} from '../../../api/receivables';
import TenantDrawer from './TenantDrawer';

const detail = {
    tenant_id: 1,
    tenant_name: 'Mayo Clinic',
    subscription: {
        id: 1, tenant_id: 1, plan: 'standard', price_kes: '18500.00', cycle: 'monthly',
        status: 'active', started_on: '2026-01-01', next_invoice_on: '2026-09-01',
        reminders_paused: false,
    },
    invoices: [
        {
            id: 11, number: 'INV-0011', period_start: '2026-07-01', period_end: '2026-07-31',
            amount_kes: '18500.00', issued_on: '2026-07-01', due_on: '2026-07-15',
            status: 'open', void_reason: null, balance: '18500.00', days_overdue: 5,
            ageing_bucket: '1-30',
        },
    ],
    payments: [],
    balances: { outstanding: '18500.00', overdue: '18500.00' },
};

describe('TenantDrawer', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        getTenantDetail.mockResolvedValue(detail);
    });

    it('loads and shows the tenant name, subscription terms, and its open invoice', async () => {
        render(<TenantDrawer tenantId={1} onClose={() => {}} onChanged={() => {}} />);
        expect(await screen.findByRole('dialog', { name: /Mayo Clinic/i })).toBeInTheDocument();
        expect(screen.getByText('INV-0011')).toBeInTheDocument();
        expect(screen.getByDisplayValue('18500.00')).toBeInTheDocument();
    });

    it('records a payment against an open invoice', async () => {
        const user = userEvent.setup();
        recordPayment.mockResolvedValue({ invoice_id: 11, status: 'paid', balance: '0.00' });
        const onChanged = vi.fn();
        render(<TenantDrawer tenantId={1} onClose={() => {}} onChanged={onChanged} />);

        await screen.findByText('INV-0011');
        await user.click(screen.getByRole('button', { name: /payment/i }));
        await user.click(screen.getByRole('button', { name: /record payment/i }));

        await waitFor(() => expect(recordPayment).toHaveBeenCalledWith(11, expect.objectContaining({ amount_kes: '18500.00' })));
        await waitFor(() => expect(onChanged).toHaveBeenCalled());
    });

    it('pauses reminders for the tenant', async () => {
        const user = userEvent.setup();
        setReminders.mockResolvedValue({ tenant_id: 1, reminders_paused: true });
        render(<TenantDrawer tenantId={1} onClose={() => {}} onChanged={() => {}} />);

        await screen.findByText('INV-0011');
        await user.click(screen.getByRole('button', { name: /pause reminders/i }));

        await waitFor(() => expect(setReminders).toHaveBeenCalledWith(1, true));
    });

    it('shows an error state when the tenant fails to load', async () => {
        getTenantDetail.mockRejectedValue({ response: { data: { detail: 'Tenant not found.' } } });
        render(<TenantDrawer tenantId={99} onClose={() => {}} onChanged={() => {}} />);
        expect(await screen.findByText('Tenant not found.')).toBeInTheDocument();
    });
});
