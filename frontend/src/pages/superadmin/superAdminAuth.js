/* Superadmin session helpers. Non-component module (plain .js) so the login
 * page can export only its component — keeps React Fast Refresh working.
 *
 * The JWT itself lives in an HttpOnly cookie ('superadmin_token') and is not
 * readable from JS — these two localStorage markers exist only to drive the UI:
 *  - NAME_KEY:    display name in the sidebar.
 *  - EXPIRES_KEY: TTL hint so the route guard can bounce expired sessions
 *                 without a round-trip; the server still has the final say
 *                 (/superadmin/me 401s and the interceptor clears everything).
 */
export const NAME_KEY = 'hms_superadmin_name';
export const EXPIRES_KEY = 'hms_superadmin_expires_at';

export const clearSuperAdminSession = () => {
    localStorage.removeItem(NAME_KEY);
    localStorage.removeItem(EXPIRES_KEY);
};

export const isSuperAdminAuthenticated = () => {
    const expiresAt = parseInt(localStorage.getItem(EXPIRES_KEY) || '0', 10);
    if (!expiresAt || Date.now() >= expiresAt) {
        clearSuperAdminSession();
        return false;
    }
    return true;
};
