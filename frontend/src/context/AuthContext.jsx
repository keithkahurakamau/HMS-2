import React, { createContext, useState, use, useEffect, useMemo } from 'react';
import { apiClient } from '../api/client';
import toast from 'react-hot-toast';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);
    const [mustChangePassword, setMustChangePassword] = useState(false);
    // AUTH-001: the forced-change flow used to stash a numeric user_id from
    // the 403 response and POST {user_id, new_password} back — which let
    // anyone rewrite anyone's password. We now carry the email + the
    // password the user just typed, and the backend re-verifies that
    // current_password against the hash before accepting a new one.
    const [pendingEmail, setPendingEmail] = useState(null);
    const [pendingPassword, setPendingPassword] = useState(null);

    useEffect(() => {
        checkAuthStatus();
    }, []);

    const checkAuthStatus = async () => {
        try {
            const response = await apiClient.get('/users/me');
            const permRes = await apiClient.get('/users/me/permissions').catch(() => ({ data: [] }));
            // Explicit pick-list instead of `...response.data` spread — the
            // backend is trusted today, but an attacker who can shape the
            // response (compromised tenant API, MITM on a downgraded link)
            // could otherwise inject `isAuthenticated:false` or arbitrary
            // permission fields into the auth state.
            const u = response.data || {};
            setUser({
                isAuthenticated: true,
                permissions: Array.isArray(permRes.data) ? permRes.data : [],
                user_id: u.user_id,
                email: u.email,
                role: u.role,
                full_name: u.full_name,
            });
        } catch (error) {
            setUser(null);
        } finally {
            setLoading(false);
        }
    };

    const login = async (email, password) => {
        try {
            await apiClient.post('/auth/login', { email, password });
            await checkAuthStatus();
            toast.success('Authentication successful');
            return { success: true };
        } catch (error) {
            const detail = error.response?.data?.detail;
            if (detail === 'PASSWORD_CHANGE_REQUIRED') {
                // Stash the credentials the operator just successfully proved
                // they hold so ChangePassword can re-submit them as the
                // current_password knowledge factor (the backend re-verifies).
                setPendingEmail(email);
                setPendingPassword(password);
                setMustChangePassword(true);
                return { success: false, mustChangePassword: true };
            }
            toast.error(detail || 'Invalid credentials');
            return { success: false };
        }
    };

    const clearMustChange = () => {
        setMustChangePassword(false);
        setPendingEmail(null);
        setPendingPassword(null);
    };

    const logout = async () => {
        try {
            await apiClient.post('/auth/logout');
        } catch (error) {
            // Even if the server call fails, proceed to clear local state
            // so a stuck session can't trap the user.
        } finally {
            setUser(null);
            localStorage.removeItem('hms_tenant_id');
            localStorage.removeItem('hms_tenant_name');
            toast.success('Logged out securely');
            // Hard redirect to the portal so the user can pick a hospital again
            // and all in-memory state is wiped.
            window.location.href = '/portal';
        }
    };

    const value = useMemo(
        () => ({ user, login, logout, loading, mustChangePassword, pendingEmail, pendingPassword, clearMustChange, refreshUser: checkAuthStatus }),
        [user, loading, mustChangePassword, pendingEmail, pendingPassword],
    );

    return (
        <AuthContext.Provider value={value}>
            {children}
        </AuthContext.Provider>
    );
};

export const useAuth = () => use(AuthContext);