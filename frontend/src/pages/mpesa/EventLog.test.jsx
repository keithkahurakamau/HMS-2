import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/renderWithProviders';

vi.mock('../../api/mpesaEvents', async () => {
    const actual = await vi.importActual('../../api/mpesaEvents');
    return {
        ...actual,
        listEvents: vi.fn(),
        getEvent: vi.fn(),
    };
});

import { listEvents, getEvent } from '../../api/mpesaEvents';
import EventLog from './EventLog';

const ROW = {
    id: 1,
    created_at: '2026-09-03T10:00:00Z',
    flow: 'stk_callback',
    direction: 'inbound',
    outcome: 'success',
    http_status: 200,
    daraja_result_code: '0',
    daraja_result_desc: 'The service request is processed successfully.',
    duration_ms: 120,
    checkout_request_id: 'ws_CO_1',
    conversation_id: null,
    receipt_number: 'QGR7XXXX01',
    phone_masked: '254***78',
    mpesa_transaction_id: 5,
    mpesa_refund_id: null,
};

const QUARANTINED_ROW = {
    ...ROW,
    id: 2,
    outcome: 'quarantined',
    daraja_result_desc: 'Callback claimed KES 60000.00, we requested KES 500.00',
};

const QUARANTINED_DETAIL = {
    ...QUARANTINED_ROW,
    phone_number: '254712345678',
    requested_amount: '500.00',
    claimed_amount: '60000.00',
    request_payload: { BusinessShortCode: '174379' },
    response_payload: { Amount: '60000.00' },
};

beforeEach(() => {
    vi.clearAllMocks();
});

describe('EventLog', () => {
    it('renders the event list with a masked phone number', async () => {
        listEvents.mockResolvedValue({ items: [ROW], total: 1, page: 1, page_size: 25 });
        renderWithProviders(<EventLog />);

        await waitFor(() => expect(listEvents).toHaveBeenCalled());
        expect(await screen.findByText('QGR7XXXX01')).toBeInTheDocument();
        expect(screen.getByText('254***78')).toBeInTheDocument();
        expect(screen.queryByText('254712345678')).not.toBeInTheDocument();
    });

    it('shows an empty state when there are no events', async () => {
        listEvents.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 25 });
        renderWithProviders(<EventLog />);

        expect(await screen.findByText(/no m-pesa events recorded yet/i)).toBeInTheDocument();
    });

    it('filters by outcome when a chip is clicked', async () => {
        listEvents.mockResolvedValue({ items: [ROW], total: 1, page: 1, page_size: 25 });
        renderWithProviders(<EventLog />);
        await waitFor(() => expect(listEvents).toHaveBeenCalledTimes(1));

        const group = screen.getByRole('group', { name: /filter by outcome/i });
        await userEvent.click(within(group).getByRole('button', { name: 'quarantined' }));

        await waitFor(() => {
            const lastCall = listEvents.mock.calls.at(-1)[0];
            expect(lastCall.outcome).toBe('quarantined');
        });
    });

    it('opens the detail drawer and shows requested vs. claimed amounts for a quarantined event', async () => {
        listEvents.mockResolvedValue({ items: [QUARANTINED_ROW], total: 1, page: 1, page_size: 25 });
        getEvent.mockResolvedValue(QUARANTINED_DETAIL);
        renderWithProviders(<EventLog />);

        await screen.findByText('QGR7XXXX01');
        await userEvent.click(screen.getByRole('button', { name: /view/i }));

        await waitFor(() => expect(getEvent).toHaveBeenCalledWith(2));
        expect(await screen.findByText(/amount claimed vs\. amount requested/i)).toBeInTheDocument();
        expect(screen.getByText('KES 500.00')).toBeInTheDocument();
        expect(screen.getByText('KES 60,000.00')).toBeInTheDocument();
        // Full phone number only appears once the detail has loaded.
        expect(screen.getByText('254712345678')).toBeInTheDocument();
    });
});
