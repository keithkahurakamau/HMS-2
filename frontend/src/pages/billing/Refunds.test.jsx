import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/renderWithProviders';

vi.mock('../../api/mpesa', () => ({
    listRefunds: vi.fn(),
    requestRefund: vi.fn(),
    approveRefund: vi.fn(),
    retryRefundDispatch: vi.fn(),
    getRefundableAmount: vi.fn(),
    getConfig: vi.fn(),
    formatKes: (v) => `KES ${v}`,
}));

vi.mock('react-hot-toast', () => ({
    default: { success: vi.fn(), error: vi.fn() },
}));

vi.mock('../../context/AuthContext', async (orig) => {
    const actual = await orig();
    return { ...actual, useAuth: () => ({ user: { user_id: 1 } }) };
});

import {
    listRefunds, requestRefund, approveRefund, retryRefundDispatch, getRefundableAmount, getConfig,
} from '../../api/mpesa';
import Refunds from './Refunds';

const CONFIG = { refund_dual_approval_above: '5000.00' };

const REFUND_BELOW_THRESHOLD = {
    id: 1, invoice_id: 10, phone_number: '254712345678', amount: '1000.00',
    reason: 'Duplicate charge', status: 'Requested', transaction_receipt: null,
    requested_by: 1, approved_by: null, requested_at: '2026-08-20T10:00:00Z',
};

const REFUND_ABOVE_THRESHOLD_SAME_REQUESTER = {
    id: 2, invoice_id: 11, phone_number: '254799999999', amount: '9000.00',
    reason: 'Overcharge', status: 'Requested', transaction_receipt: null,
    requested_by: 1, approved_by: null, requested_at: '2026-08-20T11:00:00Z',
};

const REFUND_ABOVE_THRESHOLD_OTHER_REQUESTER = {
    ...REFUND_ABOVE_THRESHOLD_SAME_REQUESTER, id: 3, requested_by: 2,
};

describe('Refunds', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        getConfig.mockResolvedValue(CONFIG);
    });

    it('lists refunds with their status', async () => {
        listRefunds.mockResolvedValue([REFUND_BELOW_THRESHOLD]);
        renderWithProviders(<Refunds />);
        expect(await screen.findByText('Duplicate charge')).toBeInTheDocument();
        expect(screen.getByRole('cell', { name: 'Requested' })).toBeInTheDocument();
    });

    it('offers approve to the requester below the dual-approval threshold', async () => {
        listRefunds.mockResolvedValue([REFUND_BELOW_THRESHOLD]);
        renderWithProviders(<Refunds />);
        await screen.findByText('Duplicate charge');
        expect(screen.getByRole('button', { name: /approve/i })).toBeInTheDocument();
    });

    it('hides approve from the requester above the dual-approval threshold', async () => {
        listRefunds.mockResolvedValue([REFUND_ABOVE_THRESHOLD_SAME_REQUESTER]);
        renderWithProviders(<Refunds />);
        await screen.findByText('Overcharge');
        expect(screen.queryByRole('button', { name: /approve/i })).not.toBeInTheDocument();
        expect(screen.getByText(/awaiting a second approver/i)).toBeInTheDocument();
    });

    it('offers approve above the threshold to a DIFFERENT user than the requester', async () => {
        listRefunds.mockResolvedValue([REFUND_ABOVE_THRESHOLD_OTHER_REQUESTER]);
        renderWithProviders(<Refunds />);
        await screen.findByText('Overcharge');
        expect(screen.getByRole('button', { name: /approve/i })).toBeInTheDocument();
    });

    it('approves a refund on click', async () => {
        listRefunds.mockResolvedValue([REFUND_BELOW_THRESHOLD]);
        approveRefund.mockResolvedValue({ ...REFUND_BELOW_THRESHOLD, status: 'Processing' });
        renderWithProviders(<Refunds />);
        await screen.findByText('Duplicate charge');

        await userEvent.click(screen.getByRole('button', { name: /approve/i }));
        await waitFor(() => expect(approveRefund).toHaveBeenCalledWith(1));
    });

    it('requests a refund against a checked transaction', async () => {
        listRefunds.mockResolvedValue([]);
        getRefundableAmount.mockResolvedValue({ refundable_amount: '2000.00' });
        requestRefund.mockResolvedValue({ id: 5, status: 'Requested' });
        renderWithProviders(<Refunds />);
        await screen.findByText(/no refunds recorded yet/i);

        await userEvent.click(screen.getByRole('button', { name: /request a refund/i }));
        const dialog = await screen.findByRole('dialog');

        await userEvent.type(screen.getByPlaceholderText(/e.g. 482/i), '42');
        await userEvent.click(screen.getByRole('button', { name: /check/i }));
        expect(await screen.findByText(/refundable up to/i)).toBeInTheDocument();

        const amountInput = dialog.querySelector('input[type="number"]');
        await userEvent.type(amountInput, '500');
        await userEvent.type(screen.getByPlaceholderText(/why this refund/i), 'Patient overcharged');

        await userEvent.click(screen.getByRole('button', { name: /^request refund$/i }));
        await waitFor(() => expect(requestRefund).toHaveBeenCalledWith({
            source_transaction_id: 42, amount: '500', reason: 'Patient overcharged',
        }));
    });

    it('offers retry-dispatch for a refund stuck at Approved, and resubmits it', async () => {
        const stuck = { ...REFUND_BELOW_THRESHOLD, id: 9, status: 'Approved' };
        listRefunds.mockResolvedValue([stuck]);
        retryRefundDispatch.mockResolvedValue({ ...stuck, status: 'Processing' });
        renderWithProviders(<Refunds />);
        await screen.findByText('Duplicate charge');

        const retryButton = screen.getByRole('button', { name: /retry dispatch/i });
        expect(retryButton).toBeInTheDocument();
        await userEvent.click(retryButton);
        await waitFor(() => expect(retryRefundDispatch).toHaveBeenCalledWith(9));
    });

    it('offers neither approve nor retry-dispatch for a refund already Processing or Completed', async () => {
        listRefunds.mockResolvedValue([
            { ...REFUND_BELOW_THRESHOLD, id: 10, status: 'Processing' },
        ]);
        renderWithProviders(<Refunds />);
        await screen.findByText('Duplicate charge');
        expect(screen.queryByRole('button', { name: /approve/i })).not.toBeInTheDocument();
        expect(screen.queryByRole('button', { name: /retry dispatch/i })).not.toBeInTheDocument();
    });
});
