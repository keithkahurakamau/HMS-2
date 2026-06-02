/* Non-component helpers for the accounting tabs. Kept in a plain .js sibling
 * (not ui.jsx) so the component file exports only components — that keeps
 * React Fast Refresh working during development. */

export const formatAmount = (v) => {
    const n = Number(v ?? 0);
    return n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};

export const todayISO = () => new Date().toISOString().slice(0, 10);
