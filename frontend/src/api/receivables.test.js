import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('./client', () => ({
    apiClient: {
        get: vi.fn(),
        post: vi.fn(),
        put: vi.fn(),
    },
}));

import { apiClient } from './client';
import {
    getSummary, getAgeing, getTenantDetail, recordPayment, voidInvoice,
    setReminders, runBillingNow, updateSubscription, formatKes, isZeroMoney,
} from './receivables';

describe('receivables api wrapper', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it('reads summary, ageing and one tenant off the superadmin receivables router', async () => {
        apiClient.get.mockResolvedValueOnce({ data: { billed: '1.00' } });
        await getSummary();
        expect(apiClient.get).toHaveBeenCalledWith('/public/superadmin/receivables/summary');

        apiClient.get.mockResolvedValueOnce({ data: [] });
        await getAgeing();
        expect(apiClient.get).toHaveBeenCalledWith('/public/superadmin/receivables/ageing');

        apiClient.get.mockResolvedValueOnce({ data: { tenant_id: 7 } });
        await getTenantDetail(7);
        expect(apiClient.get).toHaveBeenCalledWith('/public/superadmin/receivables/tenant/7');
    });

    it('posts a payment, a void reason, a reminders flag, and a billing run', async () => {
        apiClient.post.mockResolvedValue({ data: {} });

        await recordPayment(5, { amount_kes: '100.00', paid_on: '2026-08-01' });
        expect(apiClient.post).toHaveBeenCalledWith('/public/superadmin/receivables/invoice/5/payment', { amount_kes: '100.00', paid_on: '2026-08-01' });

        await voidInvoice(5, 'raised in error');
        expect(apiClient.post).toHaveBeenCalledWith('/public/superadmin/receivables/invoice/5/void', { reason: 'raised in error' });

        await setReminders(9, true);
        expect(apiClient.post).toHaveBeenCalledWith('/public/superadmin/receivables/tenant/9/reminders', { paused: true });

        await runBillingNow();
        expect(apiClient.post).toHaveBeenCalledWith('/public/superadmin/receivables/run');
    });

    it('puts subscription updates', async () => {
        apiClient.put.mockResolvedValue({ data: {} });
        await updateSubscription(3, { plan: 'premium' });
        expect(apiClient.put).toHaveBeenCalledWith('/public/superadmin/receivables/subscription/3', { plan: 'premium' });
    });

    describe('formatKes', () => {
        it('formats a decimal string with thousands separators, without ever going through Number()', () => {
            expect(formatKes('15000.00')).toBe('KES 15,000.00');
            expect(formatKes('49500.00')).toBe('KES 49,500.00');
            expect(formatKes('0.00')).toBe('KES 0.00');
            expect(formatKes('1234567.89')).toBe('KES 1,234,567.89');
        });

        it('preserves a negative sign', () => {
            expect(formatKes('-500.00')).toBe('-KES 500.00');
        });

        it('never calls Number() or parseFloat() on the input', () => {
            // A value with more precision than a float safely represents:
            // if this were routed through Number(), the digits past 15
            // significant figures would already have rounded.
            const huge = '900000000000000000.00';
            expect(formatKes(huge)).toBe('KES 900,000,000,000,000,000.00');
        });
    });

    describe('isZeroMoney', () => {
        it('recognises zero in its various decimal-string spellings', () => {
            expect(isZeroMoney('0.00')).toBe(true);
            expect(isZeroMoney('0')).toBe(true);
            expect(isZeroMoney('-0.00')).toBe(true);
        });

        it('rejects any nonzero amount', () => {
            expect(isZeroMoney('0.01')).toBe(false);
            expect(isZeroMoney('15000.00')).toBe(false);
        });
    });
});
