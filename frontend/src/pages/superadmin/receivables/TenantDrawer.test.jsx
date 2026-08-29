import React, { useState } from 'react';
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

// A tenant with no invoices/payments so the focusable elements inside the
// drawer are a short, predictable set: the Close button, "Pause reminders",
// and the three subscription-edit fields plus its Save button. That makes
// "first" and "last" unambiguous for the focus-trap tests, instead of
// depending on however many invoice action buttons happen to render.
const focusDetail = {
    tenant_id: 1,
    tenant_name: 'Mayo Clinic',
    subscription: {
        id: 1, tenant_id: 1, plan: 'standard', price_kes: '18500.00', cycle: 'monthly',
        status: 'active', started_on: '2026-01-01', next_invoice_on: '2026-09-01',
        reminders_paused: false,
    },
    invoices: [],
    payments: [],
    balances: { outstanding: '0.00', overdue: '0.00' },
};

// Renders a trigger button plus the drawer, mimicking how AgeingTable and
// Receivables actually use it: the drawer mounts only once something opens
// it, and unmounts when it closes. Lets the focus-restoration tests assert
// against a real "thing that had focus before the drawer opened".
function Harness({ onChanged = () => {} }) {
    const [open, setOpen] = useState(false);
    return (
        <>
            <button type="button" onClick={() => setOpen(true)}>Open drawer</button>
            {open && (
                <TenantDrawer tenantId={1} onClose={() => setOpen(false)} onChanged={onChanged} />
            )}
        </>
    );
}

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

    it('does not colour the overdue tile as a problem when the balance is a zero spelled differently than "0.00"', async () => {
        // "0" is the same amount as "0.00", just a different valid decimal-
        // string spelling. A hardcoded `=== '0.00'` check would miss this and
        // wrongly colour a zero balance as overdue; isZeroMoney() must not.
        getTenantDetail.mockResolvedValue({ ...detail, balances: { outstanding: '18500.00', overdue: '0' } });
        render(<TenantDrawer tenantId={1} onClose={() => {}} onChanged={() => {}} />);

        const overdueValue = await screen.findByText('KES 0.00');
        expect(overdueValue.className).not.toMatch(/rose/);
    });

    it('shows an error state when the tenant fails to load', async () => {
        getTenantDetail.mockRejectedValue({ response: { data: { detail: 'Tenant not found.' } } });
        render(<TenantDrawer tenantId={99} onClose={() => {}} onChanged={() => {}} />);
        expect(await screen.findByText('Tenant not found.')).toBeInTheDocument();
    });

    describe('focus management', () => {
        beforeEach(() => {
            getTenantDetail.mockResolvedValue(focusDetail);
        });

        it('moves focus into the dialog on open, onto the close button', async () => {
            const user = userEvent.setup();
            render(<Harness />);
            await user.click(screen.getByRole('button', { name: /open drawer/i }));

            const dialog = await screen.findByRole('dialog', { name: /Mayo Clinic/i });
            const closeButton = screen.getByRole('button', { name: 'Close' });

            await waitFor(() => expect(document.activeElement).toBe(closeButton));
            expect(dialog).toContainElement(closeButton);
        });

        it('traps Tab inside the dialog: last wraps to first, and Shift+Tab from first wraps to last', async () => {
            const user = userEvent.setup();
            render(<Harness />);
            await user.click(screen.getByRole('button', { name: /open drawer/i }));

            await screen.findByRole('dialog', { name: /Mayo Clinic/i });
            const closeButton = screen.getByRole('button', { name: 'Close' });
            const saveButton = screen.getByRole('button', { name: /save subscription/i });

            await waitFor(() => expect(document.activeElement).toBe(closeButton));

            // Shift+Tab from the first focusable element must wrap to the
            // last, not escape the dialog backwards.
            await user.tab({ shift: true });
            expect(document.activeElement).toBe(saveButton);

            // Tab from the last focusable element must wrap back to the
            // first, not escape the dialog forwards.
            await user.tab();
            expect(document.activeElement).toBe(closeButton);
        });

        it('returns focus to the trigger that opened it once the drawer closes', async () => {
            const user = userEvent.setup();
            render(<Harness />);
            const trigger = screen.getByRole('button', { name: /open drawer/i });

            await user.click(trigger);
            const closeButton = await screen.findByRole('button', { name: 'Close' });
            await waitFor(() => expect(document.activeElement).toBe(closeButton));

            await user.click(closeButton);

            await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
            expect(document.activeElement).toBe(trigger);
        });
    });
});
