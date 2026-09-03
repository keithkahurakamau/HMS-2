import { apiClient } from './client';

/**
 * Thin wrapper over the tenant's own Daraja M-Pesa surface: hospital-wide
 * till config (/api/admin/mpesa/...), the STK push + status the cashier
 * screens use (/api/payments/mpesa/...), and the B2C refund register.
 *
 * Every money field the backend returns is a decimal string (e.g.
 * "15000.00"), never a float. formatKes() below formats it for display
 * without ever routing it through Number()/parseFloat(), the same discipline
 * api/receivables.js already uses: money is formatted here, never computed.
 */
const ADMIN_BASE = '/admin/mpesa';
const PAYMENTS_BASE = '/payments/mpesa';

// ─── Hospital-wide till config ──────────────────────────────────────────────

export const getConfig = () =>
    apiClient.get(`${ADMIN_BASE}/config`).then((r) => r.data);

export const saveConfig = (payload) =>
    apiClient.post(`${ADMIN_BASE}/config`, payload).then((r) => r.data);

export const getC2bReadiness = () =>
    apiClient.get(`${ADMIN_BASE}/c2b-readiness`).then((r) => r.data);

export const registerC2b = () =>
    apiClient.post(`${ADMIN_BASE}/register-c2b`).then((r) => r.data);

export const getCallbackUrls = () =>
    apiClient.get(`${ADMIN_BASE}/callback-urls`).then((r) => r.data);

export const rotateToken = () =>
    apiClient.post(`${ADMIN_BASE}/rotate-token`).then((r) => r.data);

export const listUnmatched = () =>
    apiClient.get(`${ADMIN_BASE}/unmatched`).then((r) => r.data);

export const assignUnmatched = (transactionId, invoiceId) =>
    apiClient.post(`${ADMIN_BASE}/unmatched/${transactionId}/assign`, { invoice_id: invoiceId }).then((r) => r.data);

export const listTransactions = () =>
    apiClient.get(`${ADMIN_BASE}/transactions`).then((r) => r.data);

export const testStk = (payload) =>
    apiClient.post(`${ADMIN_BASE}/test-stk`, payload).then((r) => r.data);

// ─── STK push + status (cashier screens) ────────────────────────────────────

export const stkPush = (payload) =>
    apiClient.post(`${PAYMENTS_BASE}/stk-push`, payload).then((r) => r.data);

export const getInvoiceStatus = (invoiceId) =>
    apiClient.get(`${PAYMENTS_BASE}/invoice-status/${invoiceId}`).then((r) => r.data);

// ─── Refunds ─────────────────────────────────────────────────────────────

export const listRefunds = (status) =>
    apiClient
        .get(`${PAYMENTS_BASE}/refunds`, { params: status ? { status } : undefined })
        .then((r) => r.data);

export const requestRefund = (payload) =>
    apiClient.post(`${PAYMENTS_BASE}/refunds`, payload).then((r) => r.data);

export const approveRefund = (refundId) =>
    apiClient.post(`${PAYMENTS_BASE}/refunds/${refundId}/approve`).then((r) => r.data);

export const retryRefundDispatch = (refundId) =>
    apiClient.post(`${PAYMENTS_BASE}/refunds/${refundId}/retry-dispatch`).then((r) => r.data);

export const getRefundableAmount = (transactionId) =>
    apiClient.get(`${PAYMENTS_BASE}/transactions/${transactionId}/refundable`).then((r) => r.data);

// ─── Idempotency ─────────────────────────────────────────────────────────
//
// The charge route requires an idempotency_key per attempt: one user action
// (a click of "Send STK push", "Send test", "Request refund"...) gets one
// key, reused if that SAME attempt has to be resubmitted (a double click
// before the button disables, a dropped response retried automatically),
// and replaced with a fresh one only when the user explicitly starts a NEW
// attempt (a "Try again" after a resolved failure, a different invoice or
// amount). Reusing a key past that point would replay the FIRST attempt's
// cached response, including its now-stale checkout_request_id, instead of
// sending the customer a fresh prompt — see stk.py's own idempotent_guard,
// which caches the synchronous push acknowledgement, not the eventual
// Safaricom outcome. Callers own an idempotencyKeyRef (useRef(null)) and
// call newIdempotencyKey() to mint into it; clearing the ref back to null
// is how a caller signals "the next attempt is a new one".
export const newIdempotencyKey = () => crypto.randomUUID();

/**
 * True when a decimal-string money amount is exactly zero ("0.00", "-0.00",
 * even a bare "0"). String pattern match only, no Number()/parseFloat().
 */
export const isZeroMoney = (value) => {
    if (value == null) return true;
    return /^-?0+(\.0+)?$/.test(String(value).trim());
};

/**
 * Format a decimal-string money amount ("15000.00", "-500.5") as
 * "KES 15,000.00". Pure string manipulation: the value never passes through
 * Number()/parseFloat(), so a very large or oddly-precise balance can never
 * silently round.
 */
export const formatKes = (value) => {
    if (value == null || value === '') return '';
    const str = String(value).trim();
    const negative = str.startsWith('-');
    const unsigned = negative ? str.slice(1) : str;
    const [rawInt, rawDec = ''] = unsigned.split('.');
    const intPart = (rawInt || '0').replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    const decPart = (rawDec + '00').slice(0, 2);
    return `${negative ? '-' : ''}KES ${intPart}.${decPart}`;
};
