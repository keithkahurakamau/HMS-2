import React, { createContext, use, useEffect, useState, useCallback } from 'react';

const ThemeContext = createContext(null);

// Two independent theme scopes:
//   • `hms_theme`        — the tenant workspace (/app/*), client-controlled.
//   • `hms_admin_theme`  — the platform back-office (/superadmin/*). Operator's
//                          own preference, deliberately NOT tied to any tenant
//                          client's choice so the console looks the same no
//                          matter which hospital the operator was just in.
const STORAGE_KEY = 'hms_theme';
const ADMIN_STORAGE_KEY = 'hms_admin_theme';
const VALID_THEMES = ['light', 'dark', 'system'];

const readTheme = (key, fallback = 'system') => {
    const stored = localStorage.getItem(key);
    return VALID_THEMES.includes(stored) ? stored : fallback;
};

// Writes the resolved theme to <html>. Exported so the route-aware applier in
// App.jsx owns the DOM write — dark mode is scoped to the workspace, while
// public/auth pages are always rendered light regardless of stored/OS theme.
export const applyDocumentTheme = (resolved) => {
    const root = document.documentElement;
    if (resolved === 'dark') {
        root.classList.add('dark');
    } else {
        root.classList.remove('dark');
    }
    root.style.colorScheme = resolved;
};

const prefersDark = () =>
    window.matchMedia('(prefers-color-scheme: dark)').matches;

export const ThemeProvider = ({ children }) => {
    const [theme, setThemeState] = useState(() => readTheme(STORAGE_KEY));
    const [adminTheme, setAdminThemeState] = useState(() => readTheme(ADMIN_STORAGE_KEY));
    // Track the OS preference in state so resolved themes recompute reactively
    // when the user flips their system theme while a scope is in 'system' mode.
    const [systemDark, setSystemDark] = useState(prefersDark);

    const setTheme = useCallback((next) => {
        if (!VALID_THEMES.includes(next)) return;
        setThemeState(next);
        localStorage.setItem(STORAGE_KEY, next);
    }, []);

    const setAdminTheme = useCallback((next) => {
        if (!VALID_THEMES.includes(next)) return;
        setAdminThemeState(next);
        localStorage.setItem(ADMIN_STORAGE_KEY, next);
    }, []);

    useEffect(() => {
        const mq = window.matchMedia('(prefers-color-scheme: dark)');
        const handler = (e) => setSystemDark(e.matches);
        mq.addEventListener('change', handler);
        return () => mq.removeEventListener('change', handler);
    }, []);

    const resolve = (t) => (t === 'system' ? (systemDark ? 'dark' : 'light') : t);
    const resolved = resolve(theme);
    const resolvedAdmin = resolve(adminTheme);

    // NOTE: we intentionally do NOT write to <html> here. The route-aware
    // <ThemeApplier> (App.jsx) decides which scope's resolved value (or a
    // forced 'light' for public/auth) lands on the document.

    const value = {
        // Tenant workspace scope
        theme,
        resolved,
        setTheme,
        toggle: () => setTheme(resolved === 'dark' ? 'light' : 'dark'),
        // Platform back-office scope (independent of the tenant client)
        adminTheme,
        resolvedAdmin,
        setAdminTheme,
        toggleAdmin: () => setAdminTheme(resolvedAdmin === 'dark' ? 'light' : 'dark'),
    };

    return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
};

export const useTheme = () => {
    const ctx = use(ThemeContext);
    if (!ctx) throw new Error('useTheme must be used inside <ThemeProvider>');
    return ctx;
};
