import React, { createContext, use, useCallback, useEffect, useMemo, useState } from 'react';
import { JOURNEYS, readProgress, writeProgress } from '../journeys';
import { useAuth } from './AuthContext';

/**
 * JourneyContext — orchestrates the in-app product tour system.
 *
 *   • `progress` is a Set<string> of module keys this user has already
 *     completed or skipped. Persisted to localStorage so tours don't
 *     re-run on every page refresh.
 *   • `activeKey` is the module currently being toured, or null.
 *   • `startJourney(moduleKey)` / `skipCurrent()` / `skipAll()` /
 *     `restartAll()` are the four public verbs.
 *
 * The `useModuleJourney(moduleKey)` hook below is the convenience
 * pattern every module page uses: just call it on mount and the tour
 * fires automatically when the page is first visited.
 */

const JourneyContext = createContext(null);

export function JourneyProvider({ children }) {
    const { user } = useAuth();
    const userId = user?.user_id ?? null;

    const [progress, setProgress] = useState(() => readProgress(userId));
    const [activeKey, setActiveKey] = useState(null);

    // Reload progress when the user changes (sign-in / sign-out).
    useEffect(() => {
        setProgress(readProgress(userId));
        setActiveKey(null);
    }, [userId]);

    const persist = useCallback((next) => {
        setProgress(next);
        writeProgress(userId, next);
    }, [userId]);

    const startJourney = useCallback((moduleKey) => {
        if (!moduleKey) return;
        const steps = JOURNEYS[moduleKey];
        if (!steps || steps.length === 0) return;
        if (progress.has(moduleKey)) return; // already done — don't pester
        setActiveKey(moduleKey);
    }, [progress]);

    // Force-start a tour even if it's already been completed
    // (Settings page "Restart this tour" affordance).
    const forceStartJourney = useCallback((moduleKey) => {
        if (!moduleKey || !JOURNEYS[moduleKey]) return;
        setActiveKey(moduleKey);
    }, []);

    const completeCurrent = useCallback(() => {
        if (!activeKey) return;
        const next = new Set(progress);
        next.add(activeKey);
        persist(next);
        setActiveKey(null);
    }, [activeKey, progress, persist]);

    const skipCurrent = useCallback(() => {
        // Mark as completed too — "skip" means "don't show this again."
        completeCurrent();
    }, [completeCurrent]);

    const skipAll = useCallback(() => {
        const next = new Set(Object.keys(JOURNEYS));
        persist(next);
        setActiveKey(null);
    }, [persist]);

    const restartAll = useCallback(() => {
        persist(new Set());
        setActiveKey(null);
    }, [persist]);

    const value = useMemo(() => ({
        progress,
        activeKey,
        activeSteps: activeKey ? JOURNEYS[activeKey] || [] : [],
        startJourney,
        forceStartJourney,
        completeCurrent,
        skipCurrent,
        skipAll,
        restartAll,
        hasCompleted: (k) => progress.has(k),
    }), [progress, activeKey, startJourney, forceStartJourney, completeCurrent, skipCurrent, skipAll, restartAll]);

    return <JourneyContext.Provider value={value}>{children}</JourneyContext.Provider>;
}

export function useJourney() {
    const ctx = use(JourneyContext);
    if (!ctx) throw new Error('useJourney must be used within JourneyProvider');
    return ctx;
}

/**
 * useModuleJourney — drop-in hook for module pages.
 *
 * Call once at the top of your page component:
 *
 *     useModuleJourney('clinical');
 *
 * On first visit the tour starts after a short delay (so the page has
 * time to render its targets). Subsequent visits no-op because the
 * module is in `progress`.
 */
export function useModuleJourney(moduleKey) {
    const { startJourney, hasCompleted } = useJourney();
    useEffect(() => {
        if (hasCompleted(moduleKey)) return;
        // Defer so the page DOM has time to settle (data fetches, layout).
        const id = setTimeout(() => startJourney(moduleKey), 600);
        return () => clearTimeout(id);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [moduleKey]);
}
