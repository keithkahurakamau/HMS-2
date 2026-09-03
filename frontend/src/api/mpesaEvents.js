import { apiClient } from './client';

/**
 * The M-Pesa event log's read API: every Daraja interaction, whatever its
 * outcome, so a cashier can answer "what happened to this payment" without
 * an engineer reading application logs. See backend/app/routes/mpesa_events.py.
 *
 * Every money field is a decimal string, never a float; format it, never
 * compute with it, the same discipline api/mpesa.js already documents.
 */
const BASE = '/mpesa/events';

export const listEvents = (params = {}) =>
    apiClient.get(BASE, { params }).then((r) => r.data);

export const getEvent = (id) =>
    apiClient.get(`${BASE}/${id}`).then((r) => r.data);

export const OUTCOMES = ['success', 'failure', 'error', 'quarantined', 'rejected'];

export const FLOWS = [
    'stk_push', 'stk_query', 'stk_callback',
    'c2b_validation', 'c2b_confirmation',
    'b2c_request', 'b2c_result', 'b2c_timeout',
    'transaction_status', 'balance', 'url_registration', 'reconciliation',
];

const FLOW_LABELS = {
    stk_push: 'STK push',
    stk_query: 'STK query',
    stk_callback: 'STK callback',
    c2b_validation: 'C2B validation',
    c2b_confirmation: 'C2B confirmation',
    b2c_request: 'B2C request',
    b2c_result: 'B2C result',
    b2c_timeout: 'B2C timeout',
    transaction_status: 'Transaction status',
    balance: 'Balance',
    url_registration: 'URL registration',
    reconciliation: 'Reconciliation',
};

export const flowLabel = (flow) => FLOW_LABELS[flow] || flow;

const OUTCOME_CHIP = {
    success: 'badge-success',
    failure: 'badge-danger',
    error: 'badge-danger',
    quarantined: 'badge-warn',
    rejected: 'badge-neutral',
};

export const outcomeBadgeClass = (outcome) => OUTCOME_CHIP[outcome] || 'badge-neutral';
