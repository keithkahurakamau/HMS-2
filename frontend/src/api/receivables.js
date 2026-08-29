import { apiClient } from './client';

/**
 * Thin wrapper over the operator receivables ledger
 * (/api/public/superadmin/receivables/...). Superadmin auth rides on the
 * cookie apiClient already carries; nothing here adds headers.
 *
 * Every money field the backend returns is a decimal string (e.g.
 * "15000.00"), never a float. These functions pass that string straight
 * through; formatKes() below formats it for display without ever routing it
 * through Number()/parseFloat(), which is how a rounding error would enter
 * the console's view of a billing ledger.
 */
const BASE = '/public/superadmin/receivables';

export const getSummary = () =>
    apiClient.get(`${BASE}/summary`).then((r) => r.data);

export const getAgeing = () =>
    apiClient.get(`${BASE}/ageing`).then((r) => r.data);

export const getTenantDetail = (tenantId) =>
    apiClient.get(`${BASE}/tenant/${tenantId}`).then((r) => r.data);

export const recordPayment = (invoiceId, payload) =>
    apiClient.post(`${BASE}/invoice/${invoiceId}/payment`, payload).then((r) => r.data);

export const voidInvoice = (invoiceId, reason) =>
    apiClient.post(`${BASE}/invoice/${invoiceId}/void`, { reason }).then((r) => r.data);

export const setReminders = (tenantId, paused) =>
    apiClient.post(`${BASE}/tenant/${tenantId}/reminders`, { paused }).then((r) => r.data);

export const runBillingNow = () =>
    apiClient.post(`${BASE}/run`).then((r) => r.data);

export const updateSubscription = (tenantId, payload) =>
    apiClient.put(`${BASE}/subscription/${tenantId}`, payload).then((r) => r.data);

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
