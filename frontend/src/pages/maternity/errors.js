// Shared error-message helper for maternity forms/tabs.
//
// FastAPI validation errors (HTTP 422) return `detail` as an ARRAY of
// {loc, msg, type} objects, not a string — e.g.
//   { detail: [{ loc: ['body', 'weight_g'], msg: 'Input should be...', type: '...' }] }
// Rendering that array directly as a React child (`{err?.response?.data?.detail}`)
// throws. Other errors (403, 409, 500, network) return `detail` as a plain
// string, or omit it entirely. This normalizes any shape to a safe string.
export function errorText(err, fallback) {
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string' && detail) return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    const parts = detail.map((d) => {
      const field = Array.isArray(d?.loc) ? d.loc[d.loc.length - 1] : null;
      const msg = (d && typeof d.msg === 'string' && d.msg) || 'Invalid value';
      return field ? `${field}: ${msg}` : msg;
    });
    return parts.join('; ');
  }
  return fallback;
}
