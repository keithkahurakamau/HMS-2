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
// Silent token refresh.
//
// When a request fails with 401 because the access token expired, we attempt
// /auth/refresh exactly once. If the refresh succeeds, the original request is
// replayed transparently. We coalesce concurrent refresh attempts via a shared
// promise so a burst of 401s only triggers a single /auth/refresh round-trip.
// =====================================================================
let refreshInFlight = null;

const SKIP_REFRESH_PATHS = ['/auth/login', '/auth/refresh', '/auth/logout', '/auth/forgot-password', '/auth/reset-password'];

apiClient.interceptors.response.use(
    (response) => response,
    async (error) => {
        const original = error.config;
        const status = error.response?.status;

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
