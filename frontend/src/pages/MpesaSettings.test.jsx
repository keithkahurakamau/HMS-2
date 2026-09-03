import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../test/renderWithProviders';

vi.mock('../api/mpesa', () => ({
    getConfig: vi.fn(),
    saveConfig: vi.fn(),
    getC2bReadiness: vi.fn(),
    getCallbackUrls: vi.fn(),
    registerC2b: vi.fn(),
    rotateToken: vi.fn(),
    testStk: vi.fn(),
    newIdempotencyKey: vi.fn(() => 'idem-key-1'),
}));

vi.mock('react-hot-toast', () => ({
    default: { success: vi.fn(), error: vi.fn() },
}));

import {
    getConfig, getC2bReadiness, getCallbackUrls, registerC2b, rotateToken, testStk,
} from '../api/mpesa';
import MpesaSettings from './MpesaSettings';

const CONFIGURED = {
    configured: true,
    mpesa_active: true,
    shortcode: '600123',
    shortcode_type: 'paybill',
    environment: 'sandbox',
    has_consumer_key: true,
    has_consumer_secret: true,
    has_passkey: true,
    initiator_name: 'MediFleetOps',
    has_initiator_password: true,
    callback_token_configured: true,
    callback_token_rotated_at: '2026-08-20T10:00:00Z',
    refunds_enabled: false,
    refund_max_amount: '10000.00',
    refund_daily_cap: '50000.00',
    refund_dual_approval_above: '5000.00',
    account_reference: 'HMS-BILLING',
    transaction_desc: 'Hospital Bill Payment',
    is_active: true,
    c2b_urls_registered_at: '2026-08-20T10:00:00Z',
    last_test_at: null,
    last_test_status: null,
    last_test_message: null,
};

const READY_TILL = {
    config_id: 1, shortcode: '600123', department_id: null,
    c2b_urls_registered_at: '2026-08-20T10:00:00Z', verification_ready: true,
};

const CALLBACK_TILLS = {
    tills: [
        {
            config_id: 1, shortcode: '600123', department_id: null,
            callback_token_rotated_at: '2026-08-20T10:00:00Z',
            stk_callback_url: 'https://mayoclinic.medifleet.app/api/payments/mpesa/stk/callback/mayoclinic_db/<redacted>',
            c2b_validation_url: 'https://mayoclinic.medifleet.app/api/payments/mpesa/c2b/validation/mayoclinic_db/<redacted>',
            c2b_confirmation_url: 'https://mayoclinic.medifleet.app/api/payments/mpesa/c2b/confirmation/mayoclinic_db/<redacted>',
            status_result_url: 'https://mayoclinic.medifleet.app/api/payments/mpesa/status/result/mayoclinic_db/<redacted>',
            status_timeout_url: 'https://mayoclinic.medifleet.app/api/payments/mpesa/status/timeout/mayoclinic_db/<redacted>',
        },
    ],
};

const setup = ({ config = CONFIGURED, readiness = [READY_TILL], callbackTills = CALLBACK_TILLS } = {}) => {
    getConfig.mockResolvedValue(config);
    getC2bReadiness.mockResolvedValue(readiness);
    getCallbackUrls.mockResolvedValue(callbackTills);
};

describe('MpesaSettings', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        Object.assign(navigator, { clipboard: { writeText: vi.fn() } });
    });

    it('renders the saved shortcode and never renders a settlement bank field', async () => {
        setup();
        renderWithProviders(<MpesaSettings />);
        expect(await screen.findByDisplayValue('600123')).toBeInTheDocument();

        expect(screen.queryByText(/settlement bank/i)).not.toBeInTheDocument();
        expect(screen.queryByText(/settlement account/i)).not.toBeInTheDocument();
        expect(screen.queryByLabelText(/bank/i)).not.toBeInTheDocument();
    });

    it('shows the callback token rotation timestamp without ever showing the token itself', async () => {
        setup();
        renderWithProviders(<MpesaSettings />);
        await screen.findByDisplayValue('600123');

        expect(screen.getByText(/token last rotated/i)).toBeInTheDocument();
        expect((await screen.findAllByText(/<redacted>/)).length).toBeGreaterThan(0);
    });

    it('blocks visibly when an active till has C2B registered but is not verification-ready', async () => {
        setup({
            readiness: [{
                config_id: 1, shortcode: '600123', department_id: null,
                c2b_urls_registered_at: '2026-08-20T10:00:00Z', verification_ready: false,
            }],
        });
        renderWithProviders(<MpesaSettings />);

        expect(await screen.findByRole('alert')).toHaveTextContent(/cannot be verified/i);
    });

    it('does not show the readiness blocker when every registered till can verify', async () => {
        setup();
        renderWithProviders(<MpesaSettings />);
        await screen.findByDisplayValue('600123');

        expect(screen.queryByText(/cannot be verified/i)).not.toBeInTheDocument();
    });

    it('requires a confirm before rotating, and states the consequence', async () => {
        setup();
        rotateToken.mockResolvedValue({
            message: 'Callback token rotated.',
            urls: CALLBACK_TILLS.tills[0],
            ...CONFIGURED,
        });
        renderWithProviders(<MpesaSettings />);
        await screen.findByDisplayValue('600123');

        await userEvent.click(screen.getByRole('button', { name: /rotate callback token/i }));
        expect(rotateToken).not.toHaveBeenCalled();

        const dialog = await screen.findByRole('alertdialog');
        expect(dialog).toHaveTextContent(/invalidates every callback url/i);
        expect(dialog).toHaveTextContent(/re-register/i);

        await userEvent.click(screen.getByRole('button', { name: /^rotate token$/i }));
        await waitFor(() => expect(rotateToken).toHaveBeenCalled());

        expect(await screen.findByText(/new token, shown once/i)).toBeInTheDocument();
    });

    it('offers to re-register C2B URLs in the same rotate action', async () => {
        setup();
        rotateToken.mockResolvedValue({ message: 'ok', urls: CALLBACK_TILLS.tills[0], ...CONFIGURED });
        renderWithProviders(<MpesaSettings />);
        await screen.findByDisplayValue('600123');

        await userEvent.click(screen.getByRole('button', { name: /rotate callback token/i }));
        await screen.findByRole('alertdialog');
        // Checked by default: re-registering after a rotation is the safe default.
        expect(screen.getByRole('checkbox', { name: /re-register c2b/i })).toBeChecked();

        await userEvent.click(screen.getByRole('button', { name: /^rotate token$/i }));
        await waitFor(() => expect(registerC2b).toHaveBeenCalled());
    });

    it('sends an idempotency key with the test push', async () => {
        setup();
        testStk.mockResolvedValue({ status: 'stk_push_sent' });
        renderWithProviders(<MpesaSettings />);
        await screen.findByDisplayValue('600123');

        await userEvent.type(screen.getByLabelText(/07XXXXXXXX or 2547XXXXXXXX/i), '0712345678');
        await userEvent.click(screen.getByRole('button', { name: /send test/i }));

        await waitFor(() => expect(testStk).toHaveBeenCalledWith(
            expect.objectContaining({ phone_number: '0712345678', idempotency_key: expect.any(String) }),
        ));
    });
});
