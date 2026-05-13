import React, { createContext, useContext, useEffect, useMemo, useState, useCallback } from 'react';
import { apiClient } from '../api/client';
import { useAuth } from './AuthContext';

/* ────────────────────────────────────────────────────────────────────────── */
/*  Module entitlement context.                                               */
/*                                                                            */
/*  Fetches /api/me/modules once the user is authenticated and exposes:       */
/*    • enabled[]              → array of module keys the tenant has bought   */
/*    • catalogue[]            → full catalogue with enabled / always_on flags*/
/*    • hasModule(key)         → boolean accessor used by ModuleGuard         */
/*    • refresh()              → re-fetch (after a plan upgrade)              */
/*                                                                            */
/*  The backend gate middleware is the security boundary. This context only   */
/*  exists so the UI can hide nav items and short-circuit the route guard     */
/*  before issuing the request that would 402.                                */
/* ────────────────────────────────────────────────────────────────────────── */

const ModuleContext = createContext(null);

export const ModuleProvider = ({ children }) => {
    const { user, loading: authLoading } = useAuth();
    const [enabled, setEnabled] = useState([]);
    const [catalogue, setCatalogue] = useState([]);
    const [loading, setLoading] = useState(true);

    const fetchModules = useCallback(async () => {
        setLoading(true);
        try {
            const res = await apiClient.get('/users/me/modules');
            setEnabled(res.data?.enabled || []);
            setCatalogue(res.data?.catalogue || []);
        } catch (_e) {
            // On error, fail-open the always-on surface (server still enforces).
            setEnabled([
                'patients', 'appointments', 'dashboard', 'settings', 'support',
                'messaging', 'notifications', 'users', 'auth',
            ]);
            setCatalogue([]);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        if (authLoading) return;
        if (!user) {
            setEnabled([]);
            setCatalogue([]);
            setLoading(false);
            return;
        }
        fetchModules();
    }, [user, authLoading, fetchModules]);

    const value = useMemo(() => ({
        enabled,
        catalogue,
        loading,
        hasModule: (key) => enabled.includes(key),
        refresh: fetchModules,
    }), [enabled, catalogue, loading, fetchModules]);

    return <ModuleContext.Provider value={value}>{children}</ModuleContext.Provider>;
};

export const useModules = () => {
    const ctx = useContext(ModuleContext);
    if (!ctx) {
        throw new Error('useModules must be used within ModuleProvider');
    }
    return ctx;
};
