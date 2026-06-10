import React, { createContext, use, useEffect, useState, useCallback, useMemo } from 'react';
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

// Allow-list URLs that are safe to interpolate into `url("...")`. Tenant
// branding can ship a data:image URL (small logos) or an https:// CDN URL.
// SVG is excluded because data:image/svg+xml can carry <script>. Anything
// containing quotes/backslashes/parentheses could break out of the CSS
// value and inject arbitrary declarations, so it's rejected.
export function safeImageUrl(url) {
    if (typeof url !== 'string' || url.length === 0) return null;
    if (url.length > 5_000_000) return null;
    if (/["\\\r\n)]/.test(url)) return null;
    const dataUrl = /^data:image\/(png|jpe?g|gif|webp);base64,[A-Za-z0-9+/=]+$/i;
    const httpsUrl = /^https:\/\/[A-Za-z0-9.\-_~:/?#@!$&'*+,;=%]+$/;
    return dataUrl.test(url) || httpsUrl.test(url) ? url : null;
}

// CSS colours land in `color:` declarations, so reject anything that isn't
// a hex literal or a simple rgb()/hsl() functional form — that blocks
// "; background-image: url(evil); --x: " style breakouts.
export function safeCssColor(value) {
    if (typeof value !== 'string') return null;
    const v = value.trim();
    if (v.length > 64) return null;
    return /^#[0-9A-Fa-f]{3,8}$/.test(v) || /^(rgb|rgba|hsl|hsla)\(\s*[0-9.\s,%]+\)$/i.test(v)
        ? v
        : null;
}

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
    // Every value is allow-listed before reaching the CSSOM — a tenant cannot
    // smuggle `; background-image:url(javascript:...)` through a colour field.
    useEffect(() => {
        const root = document.documentElement;
        const primary = safeCssColor(branding.brand_primary);
        if (primary) root.style.setProperty('--brand-primary', primary);
        else root.style.removeProperty('--brand-primary');
        const accent = safeCssColor(branding.brand_accent);
        if (accent) root.style.setProperty('--brand-accent', accent);
        else root.style.removeProperty('--brand-accent');
        const bg = safeImageUrl(branding.background_data_url);
        if (bg) root.style.setProperty('--tenant-bg', `url("${bg}")`);
        else root.style.removeProperty('--tenant-bg');
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

export const useBranding = () => use(BrandingContext);
