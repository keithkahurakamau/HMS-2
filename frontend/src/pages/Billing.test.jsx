import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../test/renderWithProviders';

// ── Mocks ────────────────────────────────────────────────────────────────────
vi.mock('../api/client', () => ({
    apiClient: {
        get: vi.fn(),
        post: vi.fn(),
        put: vi.fn(),
        patch: vi.fn(),
        delete: vi.fn(),
    },
    isTenantRedirect: vi.fn(() => false),
}));

vi.mock('../api/mpesa', () => ({
    stkPush: vi.fn(),
    getInvoiceStatus: vi.fn(),
    newIdempotencyKey: vi.fn(() => 'idem-key-1'),
}));

vi.mock('react-hot-toast', () => ({
    default: { success: vi.fn(), error: vi.fn() },
}));

vi.mock('../context/AuthContext', async (orig) => {
    const actual = await orig();
    return { ...actual, useAuth: () => ({ user: { user_id: 1, permissions: [] } }) };
});

import { apiClient } from '../api/client';
import { stkPush } from '../api/mpesa';
import toast from 'react-hot-toast';
import Billing from './Billing';

// A partially-paid invoice whose balance is the textbook JS float artifact:
// 4000 - 699.8 === 3300.2000000000003 in raw JS arithmetic. Any invoice
// settled partly in cash, by cheque, or through insurance and returning for
// the rest by M-Pesa can land here; /billing/queue explicitly includes
// "Partially Paid", so this is the normal case, not an edge one.
const PARTIALLY_PAID_INVOICE = {
    invoice_id: 55,
    patient_id: 9,
    patient_name: 'Mwangi, Asha',
    patient_opd: 'OP-2026-0009',
    total_amount: 4000,
    amount_paid: 699.8,
    status: 'Partially Paid',
    billing_date: '2026-08-20',
    items: [{ id: 1, description: 'Consultation', amount: 4000, item_type: 'Consultation' }],
};

const routeGet = (url) => {
    if (url === '/billing/queue') return Promise.resolve({ data: [PARTIALLY_PAID_INVOICE] });
    if (url.startsWith('/queue/')) return Promise.resolve({ data: [] });
    if (url === '/billing/transactions') return Promise.resolve({ data: [] });
    return Promise.resolve({ data: [] });
};

describe('Billing: M-Pesa amount precision (C1)', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        apiClient.get.mockImplementation(routeGet);
    });

    it('sends a 2-decimal string amount to the M-Pesa route for a fractional partial payment, never a computed float', async () => {
        stkPush.mockResolvedValue({ checkout_request_id: 'ws_CO_1', transaction_id: 1 });
        renderWithProviders(<Billing />);

        await userEvent.click(await screen.findByText('Mwangi, Asha'));
        await userEvent.click(screen.getByRole('button', { name: /M-Pesa \(STK\)/i }));
        await userEvent.type(screen.getByPlaceholderText(/254712345678/i), '0712345678');
        await userEvent.click(screen.getByRole('button', { name: /Trigger M-Pesa STK Push/i }));

        await waitFor(() => expect(stkPush).toHaveBeenCalled());
        const payload = stkPush.mock.calls[0][0];
        expect(payload.amount).toBe('3300.20');
        expect(typeof payload.amount).toBe('string');
        expect(payload.invoice_id).toBe(55);
        expect(payload.idempotency_key).toBe('idem-key-1');
    });

    it('renders a 422 validation-error array as readable text, not a raw object, in the failure toast', async () => {
        stkPush.mockRejectedValue({
            response: {
                status: 422,
                data: {
                    detail: [
                        { type: 'decimal_parsing', loc: ['body', 'amount'], msg: 'Input should be a valid decimal', input: 3300.2000000000003 },
                    ],
                },
            },
        });
        renderWithProviders(<Billing />);

        await userEvent.click(await screen.findByText('Mwangi, Asha'));
        await userEvent.click(screen.getByRole('button', { name: /M-Pesa \(STK\)/i }));
        await userEvent.type(screen.getByPlaceholderText(/254712345678/i), '0712345678');
        await userEvent.click(screen.getByRole('button', { name: /Trigger M-Pesa STK Push/i }));

        await waitFor(() => expect(toast.error).toHaveBeenCalled());
        const message = toast.error.mock.calls[0][0];
        expect(typeof message).toBe('string');
        expect(message).toMatch(/valid decimal/i);
    });
});
