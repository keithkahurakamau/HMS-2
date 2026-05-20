import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
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

vi.mock('react-hot-toast', () => ({
    default: {
        success: vi.fn(),
        error: vi.fn(),
    },
}));

vi.mock('../utils/printTemplates', () => ({
    printPrescription: vi.fn(),
    printReceipt: vi.fn(),
}));

import { apiClient } from '../api/client';
import toast from 'react-hot-toast';
import Pharmacy from './Pharmacy';

// ── Fixtures ─────────────────────────────────────────────────────────────────
const QUEUE_FIXTURE = [
    {
        id: 'RX-1001',
        patient: 'Asha Mwangi',
        patient_id: 11,
        record_id: 51,
        op_no: 'OP-2025-0001',
        doctor: 'Dr. Otieno',
        time: '09:14',
        priority: 'High',
        allergies: 'Penicillin',
        prescriptions: [
            { drug: 'Amoxicillin 500mg', dosage: '500mg', frequency: '8h', duration: '5d' },
        ],
    },
    {
        id: 'RX-1002',
        patient: 'Brian Kamau',
        patient_id: 12,
        record_id: 52,
        op_no: 'OP-2025-0002',
        doctor: 'Dr. Wanjiru',
        time: '09:30',
        priority: 'Normal',
        prescriptions: [],
    },
];

const INVENTORY_FIXTURE = [
    {
        batch_id: 1,
        name: 'Paracetamol 500mg',
        category: 'Analgesic',
        unit_price: 10,
        quantity: 50,
        batch_number: 'PCM-A1',
    },
    {
        batch_id: 2,
        name: 'Cetirizine 10mg',
        category: 'Antihistamine',
        unit_price: 15,
        quantity: 2,
        batch_number: 'CET-B2',
    },
    {
        batch_id: 3,
        name: 'Ibuprofen 200mg',
        category: 'Analgesic',
        unit_price: 8,
        quantity: 30,
        batch_number: 'IBU-C3',
    },
];

const TRANSACTION_ROWS_FIXTURE = {
    items: [
        {
            dispense_id: 901,
            dispensed_at: '2025-05-10T10:00:00Z',
            item_name: 'Paracetamol 500mg',
            quantity: 2,
            total_cost: 20,
            amount_paid: 20,
            patient_id: null,
            payment_method: 'Cash',
            invoice_status: 'Paid',
            cashier: 'Jane',
        },
        {
            dispense_id: 902,
            dispensed_at: '2025-05-11T11:00:00Z',
            item_name: 'Cetirizine 10mg',
            quantity: 1,
            total_cost: 15,
            amount_paid: 0,
            patient_id: 22,
            payment_method: 'M-Pesa',
            invoice_status: 'Pending M-Pesa',
            cashier: 'John',
        },
    ],
};

// ── URL routing helper ───────────────────────────────────────────────────────
//
// The Pharmacy page fires several GETs on mount and during interactions:
//
//   GET  /clinical/prescriptions/pending      → Rx queue
//   GET  /pharmacy/inventory                  → OTC inventory
//   GET  /pharmacy/transactions               → Transactions ledger
//   GET  /pharmacy/dispense/:id/receipt       → Receipt JSON (cash/card path)
//   GET  /pharmacy/dispense/:id/payment-status → M-Pesa polling
//
// The helper lets each test override individual endpoints while keeping
// safe defaults for everything else. Without this, the second mount-fetch
// will throw "TypeError: Cannot read properties of undefined" if a test
// forgets to mock it.
function setupApiMocks({
    queue = QUEUE_FIXTURE,
    inventory = INVENTORY_FIXTURE,
    transactions = TRANSACTION_ROWS_FIXTURE,
    receipt = { receipt_no: 'R-1', items: [], payments: [], totals: { total: 0, paid: 0, balance: 0, status: 'Paid' } },
    paymentStatusSequence = [],
} = {}) {
    let pollIdx = 0;
    apiClient.get.mockImplementation((url) => {
        if (url === '/clinical/prescriptions/pending') {
            return Promise.resolve({ data: queue });
        }
        if (url === '/pharmacy/inventory') {
            return Promise.resolve({ data: inventory });
        }
        if (url === '/pharmacy/transactions') {
            return Promise.resolve({ data: transactions });
        }
        if (typeof url === 'string' && url.endsWith('/receipt')) {
            return Promise.resolve({ data: receipt });
        }
        if (typeof url === 'string' && url.endsWith('/payment-status')) {
            const next = paymentStatusSequence[pollIdx] ?? paymentStatusSequence[paymentStatusSequence.length - 1] ?? {};
            pollIdx += 1;
            return Promise.resolve({ data: next });
        }
        return Promise.resolve({ data: [] });
    });
}

beforeEach(() => {
    vi.clearAllMocks();
    setupApiMocks();
    // Prevent jsdom from blowing up when receipt code calls window.open.
    // Returning null also exercises the "pop-up blocked" branch safely.
    vi.spyOn(window, 'open').mockReturnValue({
        document: { open: vi.fn(), write: vi.fn(), close: vi.fn() },
        print: vi.fn(),
        onload: null,
    });
});

// ── 1. Tab navigation ────────────────────────────────────────────────────────
describe('Pharmacy — tab navigation', () => {
    it('renders with Rx tab active by default and switches to OTC when clicked', async () => {
        const user = userEvent.setup();
        renderWithProviders(<Pharmacy />);

        // Wait for initial fetches to settle so the Rx queue is rendered.
        await waitFor(() =>
            expect(apiClient.get).toHaveBeenCalledWith('/clinical/prescriptions/pending')
        );

        const rxTab = screen.getByRole('tab', { name: /Rx Fulfillment/i });
        const otcTab = screen.getByRole('tab', { name: /OTC Point of Sale/i });

        expect(rxTab).toHaveAttribute('aria-selected', 'true');
        expect(otcTab).toHaveAttribute('aria-selected', 'false');

        await user.click(otcTab);

        expect(otcTab).toHaveAttribute('aria-selected', 'true');
        expect(rxTab).toHaveAttribute('aria-selected', 'false');
        // OTC panel is the only one with an inventory search input.
        expect(screen.getByPlaceholderText(/Search pharmacy inventory/i)).toBeInTheDocument();
    });

    it('switches to Transactions and fetches /pharmacy/transactions', async () => {
        const user = userEvent.setup();
        renderWithProviders(<Pharmacy />);

        await waitFor(() =>
            expect(apiClient.get).toHaveBeenCalledWith('/pharmacy/inventory')
        );

        const txTab = screen.getByRole('tab', { name: /Transactions/i });
        await user.click(txTab);

        await waitFor(() =>
            expect(apiClient.get).toHaveBeenCalledWith(
                '/pharmacy/transactions',
                expect.objectContaining({ params: expect.objectContaining({ limit: 200 }) })
            )
        );
        expect(txTab).toHaveAttribute('aria-selected', 'true');
    });
});

// ── 2. Rx tab ────────────────────────────────────────────────────────────────
describe('Pharmacy — Rx fulfillment tab', () => {
    it('fetches /clinical/prescriptions/pending on mount and renders the queue', async () => {
        renderWithProviders(<Pharmacy />);

        await waitFor(() =>
            expect(apiClient.get).toHaveBeenCalledWith('/clinical/prescriptions/pending')
        );

        // Each queue row exposes the patient name + the Rx ID.
        expect(await screen.findByText('Asha Mwangi')).toBeInTheDocument();
        expect(screen.getByText('Brian Kamau')).toBeInTheDocument();
        expect(screen.getByText('RX-1001')).toBeInTheDocument();
        // Badge: "2 Awaiting"
        expect(screen.getByText(/2 Awaiting/i)).toBeInTheDocument();
    });

    it('renders the empty state when the queue is empty', async () => {
        setupApiMocks({ queue: [] });
        renderWithProviders(<Pharmacy />);

        expect(
            await screen.findByText(/No pending prescriptions at this time/i)
        ).toBeInTheDocument();
        expect(screen.getByText(/0 Awaiting/i)).toBeInTheDocument();
    });

    it('clicking a queue row sets the active order and shows the dispense panel', async () => {
        const user = userEvent.setup();
        renderWithProviders(<Pharmacy />);

        const row = await screen.findByText('Asha Mwangi');
        // The clickable element is the button wrapping the row.
        const rowButton = row.closest('button');
        expect(rowButton).not.toBeNull();
        await user.click(rowButton);

        // Active-order panel renders the Rx header with the order id.
        expect(await screen.findByText('Rx: RX-1001')).toBeInTheDocument();
        // Dispense panel exposes the "Dispense & close" action.
        expect(
            screen.getByRole('button', { name: /Dispense & close/i })
        ).toBeInTheDocument();
        // The prescribed drug renders inside the panel.
        expect(screen.getByText('Amoxicillin 500mg')).toBeInTheDocument();
    });
});

// ── 3. OTC inventory + cart ──────────────────────────────────────────────────
describe('Pharmacy — OTC inventory & cart', () => {
    async function openOtc(user) {
        renderWithProviders(<Pharmacy />);
        await waitFor(() =>
            expect(apiClient.get).toHaveBeenCalledWith('/pharmacy/inventory')
        );
        await user.click(screen.getByRole('tab', { name: /OTC Point of Sale/i }));
    }

    it('fetches /pharmacy/inventory on mount and renders one card per batch', async () => {
        const user = userEvent.setup();
        await openOtc(user);

        expect(await screen.findByText('Paracetamol 500mg')).toBeInTheDocument();
        expect(screen.getByText('Cetirizine 10mg')).toBeInTheDocument();
        expect(screen.getByText('Ibuprofen 200mg')).toBeInTheDocument();
    });

    it('search box filters the inventory client-side', async () => {
        const user = userEvent.setup();
        await openOtc(user);

        // Sanity: all three cards present.
        expect(await screen.findByText('Paracetamol 500mg')).toBeInTheDocument();
        expect(screen.getByText('Cetirizine 10mg')).toBeInTheDocument();

        const searchBox = screen.getByPlaceholderText(/Search pharmacy inventory/i);
        await user.type(searchBox, 'cetir');

        // Only Cetirizine remains.
        await waitFor(() => {
            expect(screen.queryByText('Paracetamol 500mg')).not.toBeInTheDocument();
        });
        expect(screen.getByText('Cetirizine 10mg')).toBeInTheDocument();
        expect(screen.queryByText('Ibuprofen 200mg')).not.toBeInTheDocument();
    });

    it('adds an item to the cart with qty=1, then increments on the second click', async () => {
        const user = userEvent.setup();
        await openOtc(user);

        // Each batch card carries its own "Add" button.
        const paracetamolCard = (await screen.findByText('Paracetamol 500mg')).closest('div');
        // walk up to the card container that holds the Add button
        const cardWithButton = paracetamolCard.parentElement?.parentElement;
        const addButton = within(cardWithButton).getByRole('button', { name: /Add/i });

        await user.click(addButton);

        // Cart badge updates to "1 Items" and a cart line for the drug appears.
        expect(await screen.findByText(/1 Items/i)).toBeInTheDocument();
        // The cart line shows "KES 10 × 1" for one unit at price 10.
        expect(screen.getByText(/KES 10 × 1/)).toBeInTheDocument();

        await user.click(addButton);

        // Quantity flipped to 2.
        await waitFor(() => {
            expect(screen.getByText(/KES 10 × 2/)).toBeInTheDocument();
        });
        expect(toast.error).not.toHaveBeenCalled();
    });

    it('adding beyond batch quantity fires an error toast and does not increment', async () => {
        const user = userEvent.setup();
        await openOtc(user);

        // Cetirizine has stock=2 — click Add three times and the third
        // attempt should be rejected.
        const cetirizineCard = (await screen.findByText('Cetirizine 10mg')).closest('div');
        const cardWithButton = cetirizineCard.parentElement?.parentElement;
        const addButton = within(cardWithButton).getByRole('button', { name: /Add/i });

        await user.click(addButton); // qty -> 1
        await user.click(addButton); // qty -> 2 (at stock cap)
        await user.click(addButton); // rejected

        // Quantity stays at 2.
        await waitFor(() => {
            expect(screen.getByText(/KES 15 × 2/)).toBeInTheDocument();
        });
        expect(toast.error).toHaveBeenCalledWith(
            expect.stringMatching(/Cannot exceed available batch stock/i)
        );
        // The forbidden third click didn't push qty to 3.
        expect(screen.queryByText(/KES 15 × 3/)).not.toBeInTheDocument();
    });
});

// ── 4. Payment flow ──────────────────────────────────────────────────────────
//
// The Pharmacy page's OTC flow is "pay straight away":
//   - Cash / Card: POST /pharmacy/dispense (per batch) → POST /dispense/:id/pay
//                  → GET /dispense/:id/receipt → printPharmacyReceipt (window.open).
//                  No modal opens.
//   - M-Pesa:     POST /pharmacy/dispense → POST /pay (method=mpesa)
//                  → opens PaymentModal in polling mode, hits
//                  /payment-status until invoice_status='Paid' or mpesa_status='Success'.
//
// These tests exercise that flow end-to-end via the OTC bar.
describe('Pharmacy — payment flow', () => {
    async function addToCartAndGetTotal(user, batchIdx = 0) {
        renderWithProviders(<Pharmacy />);
        await waitFor(() => expect(apiClient.get).toHaveBeenCalledWith('/pharmacy/inventory'));
        await user.click(screen.getByRole('tab', { name: /OTC Point of Sale/i }));

        const card = (await screen.findByText(INVENTORY_FIXTURE[batchIdx].name)).closest('div');
        const cardWithButton = card.parentElement?.parentElement;
        const addButton = within(cardWithButton).getByRole('button', { name: /Add/i });
        await user.click(addButton);

        return INVENTORY_FIXTURE[batchIdx].unit_price; // total when qty=1
    }

    it('clicking M-Pesa on a non-empty cart opens the payment modal showing the total', async () => {
        const user = userEvent.setup();

        // Dispense → invoice for the cart.
        apiClient.post.mockImplementation((url) => {
            if (url === '/pharmacy/dispense') {
                return Promise.resolve({
                    data: { dispense_id: 555, invoice_id: 999, invoice_balance: 10 },
                });
            }
            if (url === '/pharmacy/dispense/555/pay') {
                return Promise.resolve({
                    data: {
                        status: 'stk_push_sent',
                        external_reference: 'INV-999-abc',
                        payhero_reference: 'PH-77',
                        transaction_id: 77,
                        invoice_status: 'Pending M-Pesa',
                    },
                });
            }
            return Promise.resolve({ data: {} });
        });

        const total = await addToCartAndGetTotal(user);

        // Reveal the M-Pesa phone input, then send the STK push.
        await user.click(screen.getByRole('button', { name: /M-Pesa/i }));
        const phoneInput = screen.getByPlaceholderText(/07XXXXXXXX/i);
        await user.type(phoneInput, '0712345678');
        await user.click(screen.getByRole('button', { name: /Send STK/i }));

        // Modal shows up with the invoice + total. The subtitle line
        // collapses "Walk-in · Invoice #999 · KES 10" into a single text node,
        // so query that node directly to avoid colliding with the cart total.
        expect(await screen.findByText(/Collect payment/i)).toBeInTheDocument();
        expect(
            screen.getByText(new RegExp(`Invoice #999.*KES ${total}`))
        ).toBeInTheDocument();
    });

    it('cash payment posts {method:"cash", amount: total} to /dispense/:id/pay and clears the cart', async () => {
        const user = userEvent.setup();

        apiClient.post.mockImplementation((url) => {
            if (url === '/pharmacy/dispense') {
                return Promise.resolve({
                    data: { dispense_id: 200, invoice_id: 300, invoice_balance: 10 },
                });
            }
            if (url === '/pharmacy/dispense/200/pay') {
                return Promise.resolve({
                    data: { status: 'paid', invoice_status: 'Paid' },
                });
            }
            return Promise.resolve({ data: {} });
        });

        await addToCartAndGetTotal(user); // Paracetamol qty=1, total=10

        await user.click(screen.getByRole('button', { name: /Cash/i }));

        await waitFor(() => {
            expect(apiClient.post).toHaveBeenCalledWith(
                '/pharmacy/dispense/200/pay',
                expect.objectContaining({ method: 'cash', amount: 10 })
            );
        });
        await waitFor(() => {
            expect(toast.success).toHaveBeenCalledWith(expect.stringMatching(/Cash payment/i));
        });
        // Cart cleared after cash success.
        await waitFor(() => {
            expect(screen.getByText(/Cart is empty/i)).toBeInTheDocument();
        });
    });

    it('card payment posts {method:"card", amount: total} and fires the success toast', async () => {
        const user = userEvent.setup();
        // Card flow asks for an optional reference via window.prompt.
        const promptSpy = vi.spyOn(window, 'prompt').mockReturnValue('AUTH-42');

        apiClient.post.mockImplementation((url) => {
            if (url === '/pharmacy/dispense') {
                return Promise.resolve({
                    data: { dispense_id: 201, invoice_id: 301, invoice_balance: 10 },
                });
            }
            if (url === '/pharmacy/dispense/201/pay') {
                return Promise.resolve({
                    data: { status: 'paid', invoice_status: 'Paid' },
                });
            }
            return Promise.resolve({ data: {} });
        });

        await addToCartAndGetTotal(user);

        await user.click(screen.getByRole('button', { name: /Card/i }));

        await waitFor(() => {
            expect(apiClient.post).toHaveBeenCalledWith(
                '/pharmacy/dispense/201/pay',
                expect.objectContaining({ method: 'card', amount: 10 })
            );
        });
        await waitFor(() => {
            expect(toast.success).toHaveBeenCalledWith(expect.stringMatching(/Card payment/i));
        });
        expect(promptSpy).toHaveBeenCalled();
    });

    it('M-Pesa payment posts {method:"mpesa", amount, phone_number}, polls payment-status, then fires success on Paid', async () => {
        const user = userEvent.setup();

        // First poll → still pending, second poll → Paid.
        setupApiMocks({
            paymentStatusSequence: [
                { mpesa_status: 'Pending', invoice_status: 'Pending M-Pesa' },
                { mpesa_status: 'Success', invoice_status: 'Paid', mpesa_receipt_number: 'QXY123' },
            ],
        });

        apiClient.post.mockImplementation((url) => {
            if (url === '/pharmacy/dispense') {
                return Promise.resolve({
                    data: { dispense_id: 700, invoice_id: 800, invoice_balance: 10 },
                });
            }
            if (url === '/pharmacy/dispense/700/pay') {
                return Promise.resolve({
                    data: {
                        status: 'stk_push_sent',
                        external_reference: 'INV-800-xyz',
                        payhero_reference: 'PH-7700',
                        transaction_id: 7700,
                        invoice_status: 'Pending M-Pesa',
                    },
                });
            }
            return Promise.resolve({ data: {} });
        });

        await addToCartAndGetTotal(user);

        // Trigger M-Pesa.
        await user.click(screen.getByRole('button', { name: /M-Pesa/i }));
        const phoneInput = screen.getByPlaceholderText(/07XXXXXXXX/i);
        await user.type(phoneInput, '0712345678');
        await user.click(screen.getByRole('button', { name: /Send STK/i }));

        // Verify /pay was hit with method:'mpesa'.
        await waitFor(() => {
            expect(apiClient.post).toHaveBeenCalledWith(
                '/pharmacy/dispense/700/pay',
                expect.objectContaining({
                    method: 'mpesa',
                    amount: 10,
                    phone_number: '0712345678',
                })
            );
        });

        // The polling loop fires every 3s. Real timers + a generous waitFor
        // is the deadlock-free path that the task explicitly calls out.
        await waitFor(
            () => {
                expect(apiClient.get).toHaveBeenCalledWith(
                    '/pharmacy/dispense/700/payment-status'
                );
            },
            { timeout: 5000 }
        );

        // Eventually the second poll's "Success" lands and the success toast fires.
        await waitFor(
            () => {
                expect(toast.success).toHaveBeenCalledWith(
                    expect.stringMatching(/M-Pesa receipt/i)
                );
            },
            { timeout: 10000 }
        );
    }, 15000);

    it('surfaces server-side detail in an error toast when /pay returns 400', async () => {
        const user = userEvent.setup();

        apiClient.post.mockImplementation((url) => {
            if (url === '/pharmacy/dispense') {
                return Promise.resolve({
                    data: { dispense_id: 444, invoice_id: 555, invoice_balance: 10 },
                });
            }
            if (url === '/pharmacy/dispense/444/pay') {
                const err = new Error('Request failed with status code 400');
                err.response = { status: 400, data: { detail: 'Insufficient float on till.' } };
                return Promise.reject(err);
            }
            return Promise.resolve({ data: {} });
        });

        await addToCartAndGetTotal(user);

        await user.click(screen.getByRole('button', { name: /Cash/i }));

        await waitFor(() => {
            expect(toast.error).toHaveBeenCalledWith('Insufficient float on till.');
        });
    });
});

// ── 5. Transactions ledger ───────────────────────────────────────────────────
describe('Pharmacy — transactions ledger', () => {
    async function openTransactions(user) {
        renderWithProviders(<Pharmacy />);
        await waitFor(() =>
            expect(apiClient.get).toHaveBeenCalledWith('/pharmacy/inventory')
        );
        await user.click(screen.getByRole('tab', { name: /Transactions/i }));
    }

    it('renders rows when /pharmacy/transactions returns items', async () => {
        const user = userEvent.setup();
        await openTransactions(user);

        // Two ledger rows from the fixture.
        expect(await screen.findByText('Paracetamol 500mg')).toBeInTheDocument();
        expect(screen.getByText('Cetirizine 10mg')).toBeInTheDocument();
        // Status pills. The text "Paid" also appears inside the Status
        // filter <select>; scope to the ledger table to avoid that collision.
        const tableBody = screen.getByRole('table').querySelector('tbody');
        expect(within(tableBody).getByText('Paid')).toBeInTheDocument();
        expect(within(tableBody).getByText('Pending M-Pesa')).toBeInTheDocument();
    });

    it('changing the method filter refetches /pharmacy/transactions with params.method', async () => {
        const user = userEvent.setup();
        await openTransactions(user);

        // Wait for initial transactions load.
        await waitFor(() =>
            expect(apiClient.get).toHaveBeenCalledWith(
                '/pharmacy/transactions',
                expect.any(Object)
            )
        );

        // The method filter is a <select> labelled "Method".
        const methodSelect = screen.getByLabelText(/Method/i);
        await user.selectOptions(methodSelect, 'M-Pesa');

        // Apply triggers the refetch.
        await user.click(screen.getByRole('button', { name: /Apply/i }));

        await waitFor(() => {
            expect(apiClient.get).toHaveBeenCalledWith(
                '/pharmacy/transactions',
                expect.objectContaining({
                    params: expect.objectContaining({ method: 'M-Pesa' }),
                })
            );
        });
    });

    it('renders the empty state when items: []', async () => {
        const user = userEvent.setup();
        setupApiMocks({ transactions: { items: [] } });
        await openTransactions(user);

        expect(
            await screen.findByText(/No transactions in this window/i)
        ).toBeInTheDocument();
    });
});
