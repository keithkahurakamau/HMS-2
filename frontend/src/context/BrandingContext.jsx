import React, { createContext, useContext, useEffect, useState, useCallback, useMemo } from 'react';
import { apiClient } from '../api/client';

/**
 * BrandingContext — single source of truth for the active tenant's branding.
 *
 *  Source of data
 *  --------------
 *   - When the user is authenticated, we hit GET /api/branding (uses the cookie
 *     + X-Tenant-ID header).
 *   - Before login (Portal already set hms_tenant_id), we fall back to the
 *     public endpoint GET /api/public/branding/{db_name} so the Login screen
 *     can render the right logo + background image.
 *   - With no tenant context at all (Landing page), we expose null and
 *     surfaces fall back to the platform default.
 *
 *  Reload triggers
 *  ---------------
 *   - On mount.
 *   - On `window.storage` events for ``hms_tenant_id`` (Portal switch in
 *     another tab).
 *   - Imperatively, via the ``refresh()`` callback (Settings → Branding tab
 *     calls this after a successful PUT).
 */

const DEFAULT_STATE = {
    logo_data_url: null,
    background_data_url: null,
    brand_primary: null,
    brand_accent: null,
    print_templates: {},
    tenant_name: null,
};

const BrandingContext = createContext({
    branding: DEFAULT_STATE,
    isLoading: false,
    refresh: () => {},
    updateLocal: () => {},
});

export function BrandingProvider({ children }) {
    const [branding, setBranding] = useState(DEFAULT_STATE);
    const [isLoading, setIsLoading] = useState(false);

    const fetchBranding = useCallback(async () => {
        const tenantId = localStorage.getItem('hms_tenant_id');
        if (!tenantId) {
            setBranding(DEFAULT_STATE);
            return;
        }
        setIsLoading(true);
        try {
            // Try the authenticated endpoint first; falls through to public if 401.
            try {
                const res = await apiClient.get('/branding');
                setBranding({ ...DEFAULT_STATE, ...res.data });
                return;
            } catch (err) {
                if (err?.response?.status !== 401) throw err;
            }
            const pub = await apiClient.get(`/public/branding/${tenantId}`);
            setBranding({ ...DEFAULT_STATE, ...pub.data });
        } catch {
            setBranding(DEFAULT_STATE);
        } finally {
            setIsLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchBranding();
        // Cross-tab tenant switch
        const onStorage = (e) => {
            if (e.key === 'hms_tenant_id') fetchBranding();
        };
        window.addEventListener('storage', onStorage);
        return () => window.removeEventListener('storage', onStorage);
    }, [fetchBranding]);

    // Inject brand colours + tenant background as CSS variables. Surfaces opt
    // in via the .bg-tenant utility (defined in index.css) and var(--brand-*).
    useEffect(() => {
        const root = document.documentElement;
        if (branding.brand_primary) root.style.setProperty('--brand-primary', branding.brand_primary);
        else root.style.removeProperty('--brand-primary');
        if (branding.brand_accent) root.style.setProperty('--brand-accent', branding.brand_accent);
        else root.style.removeProperty('--brand-accent');
        if (branding.background_data_url) {
            root.style.setProperty('--tenant-bg', `url("${branding.background_data_url}")`);
        } else {
            root.style.removeProperty('--tenant-bg');
        }
    }, [branding.brand_primary, branding.brand_accent, branding.background_data_url]);

    const updateLocal = useCallback((next) => {
        setBranding((prev) => ({ ...prev, ...next }));
    }, []);

    const value = useMemo(
        () => ({ branding, isLoading, refresh: fetchBranding, updateLocal }),
        [branding, isLoading, fetchBranding, updateLocal],
    );

    return <BrandingContext.Provider value={value}>{children}</BrandingContext.Provider>;
}

export const useBranding = () => useContext(BrandingContext);
