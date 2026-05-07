import React, { createContext, useState, useContext, useEffect } from 'react';
import { apiClient } from '../api/client';
import toast from 'react-hot-toast';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);
    const [mustChangePassword, setMustChangePassword] = useState(false);
    const [pendingUserId, setPendingUserId] = useState(null);

    useEffect(() => {
        checkAuthStatus();
    }, []);

    const checkAuthStatus = async () => {
        try {
            const response = await apiClient.get('/users/me');
            const permRes = await apiClient.get('/users/me/permissions').catch(() => ({ data: [] }));
            setUser({
                isAuthenticated: true,
                permissions: permRes.data || [],
                ...response.data
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
                const userId = parseInt(error.response?.headers?.['x-user-id']);
                setPendingUserId(userId);
                setMustChangePassword(true);
                return { success: false, mustChangePassword: true };
            }
            toast.error(detail || 'Invalid credentials');
            return { success: false };
        }
    };

    const clearMustChange = () => {
        setMustChangePassword(false);
        setPendingUserId(null);
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
            // Hard redirect to the welcome/Portal page so all in-memory state is wiped.
            window.location.href = '/';
        }
    };

    return (
        <AuthContext.Provider value={{ user, login, logout, loading, mustChangePassword, pendingUserId, clearMustChange }}>
            {children}
        </AuthContext.Provider>
    );
};

export const useAuth = () => useContext(AuthContext);