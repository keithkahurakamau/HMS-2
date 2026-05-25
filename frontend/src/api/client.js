import axios from 'axios';

// Endpoints served by the platform router. Used by the 401 response handler
// to know "don't try the tenant /auth/refresh dance — this is a superadmin
// path and refresh works differently" (the superadmin cookie has no refresh
// counterpart; the 20-minute TTL is hard).
const SUPERADMIN_PATH_PREFIXES = ['/public/superadmin', '/public/hospitals'];

const isSuperAdminPath = (url) => {
    if (!url) return false;
    return SUPERADMIN_PATH_PREFIXES.some((p) => url.startsWith(p) || url.includes(p));
};

const clearSuperAdminLocal = () => {
    localStorage.removeItem('hms_superadmin_name');
    localStorage.removeItem('hms_superadmin_expires_at');
};

export const apiClient = axios.create({
    baseURL: '/api',
    withCredentials: true, // CRITICAL: This ensures the secure cookies are sent with every request
    xsrfCookieName: 'csrf_token', // Extracts token from this cookie
    xsrfHeaderName: 'X-CSRF-Token', // Attaches to this header
    headers: {
        'Content-Type': 'application/json',
    }
});

// Inject Tenant ID into every request. The superadmin JWT used to be smuggled
// in as a Bearer header from localStorage — that's gone, the cookie does the
// authentication now and Axios's `withCredentials: true` carries it
// automatically. Anything an XSS could once steal from localStorage now lives
// in HttpOnly cookie space.
apiClient.interceptors.request.use((config) => {
    const tenantId = localStorage.getItem('hms_tenant_id');
    if (tenantId) {
        config.headers['X-Tenant-ID'] = tenantId;
    }
    return config;
}, (error) => {
    return Promise.reject(error);
});

// =====================================================================
// Silent token refresh + global tenant guard.
//
// When a request fails with 401 because the access token expired, we attempt
// /auth/refresh exactly once. If the refresh succeeds, the original request is
// replayed transparently. We coalesce concurrent refresh attempts via a shared
// promise so a burst of 401s only triggers a single /auth/refresh round-trip.
//
// Global tenant guard: when the backend reports the X-Tenant-ID header is
// missing (HTTP 400 from get_db), redirect to /portal so the user can pick a
// hospital instead of every page firing its own "Failed to load …" toast. The
// guard fires at most once per page load to avoid a navigation storm when
// several requests race in.
// =====================================================================
let refreshInFlight = null;
let tenantRedirectFired = false;

const SKIP_REFRESH_PATHS = ['/auth/login', '/auth/refresh', '/auth/logout', '/auth/forgot-password', '/auth/reset-password'];

// Pages that should be allowed to render even without a tenant selected.
// Anything else gets redirected to /portal when the X-Tenant-ID guard trips.
//
// Landing (`/`) belongs here even though it's a single-character path: the
// root-mounted providers (AuthContext, BrandingContext, ModuleContext) all
// fire their bootstrap fetches on every SPA mount, and a fresh visitor on
// medifleet.app legitimately has no cookie + no tenant. The 400 response
// from /users/me must NOT bounce them to the hospital picker — that's the
// "the first page should be the landing page" regression we saw post-PR-#35.
const TENANT_OPTIONAL_PATHS = ['/portal', '/login', '/superadmin', '/patient', '/forgot-password', '/reset-password'];

const isTenantOptionalPath = (pathname) => {
    if (pathname === '/') return true; // Landing — see comment above.
    return TENANT_OPTIONAL_PATHS.some(p => pathname === p || pathname.startsWith(`${p}/`));
};

const isTenantMissingError = (status, detail) =>
    status === 400 && typeof detail === 'string' && /X-Tenant-ID/i.test(detail);

// FastAPI 422s carry `detail` as an array of validation error objects:
//   [{ type, loc, msg, input }, ...]
// React components blow up when those land in JSX (e.g. `toast.error(detail)`
// → "Objects are not valid as a React child"). Flatten to a readable string
// here so every `err.response.data.detail` callsite behaves the same.
const normalizeFastApiDetail = (data) => {
    const detail = data?.detail;
    if (Array.isArray(detail)) {
        const summary = detail
            .map((d) => {
                if (typeof d === 'string') return d;
                if (d && typeof d === 'object') {
                    const field = Array.isArray(d.loc) ? d.loc.filter(p => p !== 'body').join('.') : '';
                    const msg = d.msg || d.message || JSON.stringify(d);
                    return field ? `${field}: ${msg}` : msg;
                }
                return String(d);
            })
            .join('; ');
        data.detail = summary || 'Validation error';
    } else if (detail && typeof detail === 'object') {
        data.detail = detail.msg || detail.message || JSON.stringify(detail);
    }
};

apiClient.interceptors.response.use(
    (response) => response,
    async (error) => {
        const original = error.config;
        const status = error.response?.status;
        // Reshape FastAPI validation errors BEFORE downstream reads them.
        if (error.response?.data) normalizeFastApiDetail(error.response.data);
        const detail = error.response?.data?.detail;

        // ── Tenant guard: redirect to /portal on missing X-Tenant-ID ─────────
        // This is the source of most "Failed to load …" toasts on production
        // deployments where a fresh tab opens before the user picks a hospital.
        // Redirecting once is much cleaner than every page firing its own
        // error UI.
        // Stale-tenant guard (TENANT-DRIFT-003): when localStorage still
        // holds an `hms_tenant_id` for a hospital whose DB was dropped (a
        // post-wipe browser, or a tenant deleted via the superadmin UI),
        // the backend's get_db() probes the connection and returns
        // 410 Gone with detail "tenant_not_found". Clear the dead pointer
        // so the visitor doesn't keep poking a deleted DB on every navigation.
        if (status === 410 && detail === 'tenant_not_found'
            && typeof window !== 'undefined'
        ) {
            localStorage.removeItem('hms_tenant_id');
        }

        if ((isTenantMissingError(status, detail)
                || (status === 410 && detail === 'tenant_not_found'))
            && !tenantRedirectFired
            && typeof window !== 'undefined'
            && !isTenantOptionalPath(window.location.pathname)
            && !isSuperAdminPath(original?.url)
        ) {
            tenantRedirectFired = true;
            // Soft redirect — preserve where we wanted to go so portal can
            // bounce back. URL-encode so query strings survive the round trip.
            const back = encodeURIComponent(window.location.pathname + window.location.search);
            window.location.assign(`/portal?next=${back}`);
            // Don't reject — we're navigating away. Resolve with an empty
            // shape so any pending UI code can finish without throwing.
            return Promise.reject(new axios.Cancel('Redirecting to portal — no tenant selected'));
        }

        if (!original || status !== 401) {
            return Promise.reject(error);
        }
        if (original._retried) {
            return Promise.reject(error);
        }
        if (SKIP_REFRESH_PATHS.some((p) => original.url?.includes(p))) {
            return Promise.reject(error);
        }

        // Superadmin sessions don't participate in the cookie-based refresh
        // dance — a 401 there means the 20-minute platform JWT expired (or
        // the cookie was cleared). Wipe the local UI markers so the next
        // SuperAdminProtectedRoute render bounces back to /superadmin/login.
        if (isSuperAdminPath(original.url)) {
            clearSuperAdminLocal();
            return Promise.reject(error);
        }

        try {
            if (!refreshInFlight) {
                refreshInFlight = apiClient.post('/auth/refresh').finally(() => {
                    refreshInFlight = null;
                });
            }
            await refreshInFlight;
            original._retried = true;
            return apiClient(original);
        } catch (refreshError) {
            return Promise.reject(error);
        }
    }
);

// Cleanly swallow the cancellation we issue from the tenant guard so it
// doesn't surface to per-page error handlers as a generic network error.
export const isTenantRedirect = (err) => axios.isCancel(err);
