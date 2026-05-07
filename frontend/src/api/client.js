import axios from 'axios';

export const apiClient = axios.create({
    baseURL: '/api',
    withCredentials: true, // CRITICAL: This ensures the secure cookies are sent with every request
    xsrfCookieName: 'csrf_token', // Extracts token from this cookie
    xsrfHeaderName: 'X-CSRF-Token', // Attaches to this header
    headers: {
        'Content-Type': 'application/json',
    }
});

// Inject Tenant ID into every request
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
