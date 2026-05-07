import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';

const ThemeContext = createContext(null);

const STORAGE_KEY = 'hms_theme';
const VALID_THEMES = ['light', 'dark', 'system'];

const applyDocumentTheme = (resolved) => {
    const root = document.documentElement;
    if (resolved === 'dark') {
        root.classList.add('dark');
    } else {
        root.classList.remove('dark');
    }
    root.style.colorScheme = resolved;
};

const resolveTheme = (theme) => {
    if (theme === 'system') {
        return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }
    return theme;
};

export const ThemeProvider = ({ children }) => {
    const [theme, setThemeState] = useState(() => {
        const stored = localStorage.getItem(STORAGE_KEY);
        return VALID_THEMES.includes(stored) ? stored : 'system';
    });

    const setTheme = useCallback((next) => {
        if (!VALID_THEMES.includes(next)) return;
        setThemeState(next);
        localStorage.setItem(STORAGE_KEY, next);
    }, []);

    // Apply on mount + whenever theme changes
    useEffect(() => {
        applyDocumentTheme(resolveTheme(theme));
    }, [theme]);

    // Re-apply if the OS preference flips and we're on 'system'
    useEffect(() => {
        if (theme !== 'system') return;
        const mq = window.matchMedia('(prefers-color-scheme: dark)');
        const handler = () => applyDocumentTheme(resolveTheme('system'));
        mq.addEventListener('change', handler);
        return () => mq.removeEventListener('change', handler);
    }, [theme]);

    const value = {
        theme,
        resolved: resolveTheme(theme),
        setTheme,
        toggle: () => setTheme(resolveTheme(theme) === 'dark' ? 'light' : 'dark'),
    };

    return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
};

export const useTheme = () => {
    const ctx = useContext(ThemeContext);
    if (!ctx) throw new Error('useTheme must be used inside <ThemeProvider>');
    return ctx;
};
