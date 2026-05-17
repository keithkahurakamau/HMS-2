import axios from 'axios';

// Endpoints served by the platform router that the superadmin Bearer token
// authenticates against. Any URL matching these prefixes is treated as a
// "superadmin call" — both for header injection and for token-expiry handling.
const SUPERADMIN_PATH_PREFIXES = ['/public/superadmin', '/public/hospitals'];

const isSuperAdminPath = (url) => {
    if (!url) return false;
    return SUPERADMIN_PATH_PREFIXES.some((p) => url.startsWith(p) || url.includes(p));
};

const clearSuperAdminLocal = () => {
    localStorage.removeItem('hms_superadmin_token');
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

// Inject Tenant ID into every request, plus the superadmin Bearer token when
// the operator is signed in to the platform console. The Bearer header is only
// attached to platform paths so a 401 from a tenant endpoint (e.g. /users/me on
// app boot) cannot be misread as "superadmin token expired".
apiClient.interceptors.request.use((config) => {
    const tenantId = localStorage.getItem('hms_tenant_id');
    if (tenantId) {
        config.headers['X-Tenant-ID'] = tenantId;
    }

    if (isSuperAdminPath(config.url)) {
        const superAdminToken = localStorage.getItem('hms_superadmin_token');
        const expiresAt = parseInt(localStorage.getItem('hms_superadmin_expires_at') || '0', 10);
        if (superAdminToken) {
            // Drop tokens we already know are expired to avoid an unnecessary 401.
            if (expiresAt && Date.now() >= expiresAt) {
                clearSuperAdminLocal();
            } else if (!config.headers['Authorization']) {
                config.headers['Authorization'] = `Bearer ${superAdminToken}`;
            }
        }
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
const TENANT_OPTIONAL_PATHS = ['/portal', '/login', '/superadmin', '/patient', '/forgot-password', '/reset-password'];

const isTenantOptionalPath = (pathname) =>
    TENANT_OPTIONAL_PATHS.some(p => pathname === p || pathname.startsWith(`${p}/`));

const isTenantMissingError = (status, detail) =>
    status === 400 && typeof detail === 'string' && /X-Tenant-ID/i.test(detail);

// FastAPI 422s carry `detail` as an array of validation error objects:
//   [{ type, loc, msg, input }, ...]
// React components blow up when those land in JSX (e.g. `toast.error(detail)`).
// Flatten to a readable string here so the 75-odd `err.response.data.detail`
// callsites all behave the same way.
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
        // Mutate in place — interceptor downstream + callers read the same object.
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
        // Reshape FastAPI validation errors BEFORE anything downstream reads them.
        if (error.response?.data) normalizeFastApiDetail(error.response.data);
        const detail = error.response?.data?.detail;

        // ── Tenant guard: redirect to /portal on missing X-Tenant-ID ─────────
        // This is the source of most "Failed to load …" toasts on production
        // deployments where a fresh tab opens before the user picks a hospital.
        // Redirecting once is much cleaner than every page firing its own
        // error UI.
        if (isTenantMissingError(status, detail)
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

        // Superadmin tokens don't participate in the cookie-based refresh dance.
        // Only platform-prefixed URLs use the Bearer token — a 401 there means
        // the bearer expired, so wipe it and let SuperAdminProtectedRoute kick
        // the user back to /superadmin/login on the next render.
        if (isSuperAdminPath(original.url)) {
            if (localStorage.getItem('hms_superadmin_token')) {
                clearSuperAdminLocal();
            }
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
