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
            setUser(null);
            toast.success('Logged out securely');
        } catch (error) {
            toast.error('Logout failed');
        }
    };

    return (
        <AuthContext.Provider value={{ user, login, logout, loading, mustChangePassword, pendingUserId, clearMustChange }}>
            {children}
        </AuthContext.Provider>
    );
};

export const useAuth = () => useContext(AuthContext);