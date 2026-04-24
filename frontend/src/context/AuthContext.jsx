import React, { createContext, useState, useContext, useEffect } from 'react';
import { apiClient } from '../api/client';
import toast from 'react-hot-toast';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        checkAuthStatus();
    }, []);

    const checkAuthStatus = async () => {
        try {
            // Try to fetch the full user profile (which includes the role)
            const response = await apiClient.get('/users/me');
            
            // We also fetch permissions separately just to be safe
            let permissions = [];
            try {
                const permRes = await apiClient.get('/users/me/permissions');
                permissions = permRes.data || [];
            } catch (e) {
                console.warn("Could not fetch permissions, defaulting to empty array.");
            }

            setUser({ 
                isAuthenticated: true, 
                permissions: permissions,
                ...response.data 
            });
        } catch (error) {
            setUser(null); // Invalid session/cookie
        } finally {
            setLoading(false);
        }
    };

    const login = async (email, password) => {
        try {
            // 1. Authenticate with the backend
            await apiClient.post('/auth/login', { email, password });
            
            // 2. Fetch the full profile (crucial for getting user.role)
            await checkAuthStatus();
            
            toast.success('Authentication successful');
            return true;
        } catch (error) {
            const message = error.response?.data?.detail || 'Invalid credentials';
            toast.error(message);
            return false;
        }
    };

    const logout = async () => {
        try {
            // If using cookies, call your backend logout endpoint here to destroy it
            // await apiClient.post('/auth/logout');
            setUser(null);
            toast.success('Logged out securely');
        } catch (error) {
            toast.error('Logout failed');
        }
    };

    return (
        <AuthContext.Provider value={{ user, login, logout, loading }}>
            {children}
        </AuthContext.Provider>
    );
};

export const useAuth = () => useContext(AuthContext);