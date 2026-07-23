// Shared error-message helper for theatre forms/tabs. FastAPI 422 returns
// `detail` as an array of {loc, msg, type}; other errors return a string or
// omit it. Normalize any shape to a safe string (see dialysis/errors.js).
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
