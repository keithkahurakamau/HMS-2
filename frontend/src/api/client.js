import axios from 'axios';

export const apiClient = axios.create({
    baseURL: 'http://127.0.0.1:8000/api',
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