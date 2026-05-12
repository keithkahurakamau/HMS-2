import React, { useEffect, useRef, useState } from 'react';
import { apiClient } from '../api/client';
import { useBranding } from '../context/BrandingContext';
import {
    Palette, Image as ImageIcon, Upload, Trash2, Save, Activity,
    Printer, Eye, ArrowLeft, CheckCircle2, AlertTriangle,
} from 'lucide-react';
import toast from 'react-hot-toast';
import { Link } from 'react-router-dom';
import Logo, { TenantLogo } from '../components/Logo';
import PageHeader from '../components/PageHeader';

/**
 * Branding Studio — hospital admins customise their workspace identity.
 *
 *  - Upload a custom logo (PNG/JPG/SVG, max 600 KB after compression).
 *  - Upload a sign-in background image (max 800 KB after compression).
 *  - Override the platform's primary/accent brand colours.
 *  - Configure printed-document templates (header, footer, layout style).
 *
 *  Today: images are stored base64-encoded in the master ``tenants`` row.
 *  Tomorrow: the same column will hold a Cloudinary URL — the UI doesn't
 *  change.
 */

const MAX_LOGO_BYTES = 600_000;
const MAX_BG_BYTES   = 900_000;
const TEMPLATE_OPTIONS = [
    { key: 'modern',  label: 'Modern',  hint: 'Bold header band, sans-serif, light grid' },
    { key: 'classic', label: 'Classic', hint: 'Centered crest, serif body, ruled lines' },
    { key: 'minimal', label: 'Minimal', hint: 'No header, mono accent, dense layout' },
];

export default function Branding() {
    const { branding, refresh, updateLocal } = useBranding();
    const [draft, setDraft] = useState({});
    const [saving, setSaving] = useState(false);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        (async () => {
            try {
                await refresh();
            } finally {
                setLoading(false);
            }
        })();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    // Promote remote state to draft once on hydrate so cancel/restore works.
    useEffect(() => {
        setDraft({
            logo_data_url: branding.logo_data_url,
            background_data_url: branding.background_data_url,
            brand_primary: branding.brand_primary || '',
            brand_accent: branding.brand_accent || '',
            print_templates: branding.print_templates || {},
        });
    }, [branding.logo_data_url, branding.background_data_url, branding.brand_primary,
        branding.brand_accent, branding.print_templates]);

    const set = (key, value) => setDraft((d) => ({ ...d, [key]: value }));
    const setTemplate = (key, value) =>
        setDraft((d) => ({ ...d, print_templates: { ...(d.print_templates || {}), [key]: value } }));

    const isDirty = JSON.stringify(draft) !== JSON.stringify({
        logo_data_url: branding.logo_data_url,
        background_data_url: branding.background_data_url,
        brand_primary: branding.brand_primary || '',
        brand_accent: branding.brand_accent || '',
        print_templates: branding.print_templates || {},
    });

    const handleSave = async () => {
        setSaving(true);
        try {
            const payload = {
                brand_primary: draft.brand_primary || '',
                brand_accent: draft.brand_accent || '',
                print_templates: {
                    header_text: draft.print_templates?.header_text || '',
                    footer_text: draft.print_templates?.footer_text || '',
                    primary_template: draft.print_templates?.primary_template || 'modern',
                    show_logo: draft.print_templates?.show_logo !== false,
                },
            };
            // Image fields only attach when changed, or as explicit clears.
            if (draft.logo_data_url !== branding.logo_data_url) {
                if (!draft.logo_data_url) payload.clear_logo = true;
                else payload.logo_data_url = draft.logo_data_url;
            }
            if (draft.background_data_url !== branding.background_data_url) {
                if (!draft.background_data_url) payload.clear_background = true;
                else payload.background_data_url = draft.background_data_url;
            }
            const res = await apiClient.put('/branding', payload);
            updateLocal(res.data);
            toast.success('Branding saved.');
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Failed to save branding.');
        } finally {
            setSaving(false);
        }
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center py-24 text-ink-400">
                <Activity className="animate-spin mr-2" size={20} /> Loading branding…
            </div>
        );
    }

    return (
        <div className="space-y-6 animate-fade-in">
            <Link to="/app/settings" className="inline-flex items-center gap-1 text-2xs font-semibold uppercase tracking-[0.14em] text-ink-500 hover:text-brand-700 transition-colors cursor-pointer -mb-3">
                <ArrowLeft size={12} /> Settings
            </Link>
            <PageHeader
                eyebrow="Studio"
                icon={Palette}
                title="Branding Studio"
                subtitle="Customise your workspace identity. Uploads are stored in the platform DB for now and will transparently migrate to Cloudinary later."
                meta={isDirty && (
                    <span className="badge-warn">
                        <AlertTriangle size={11} /> Unsaved changes
                    </span>
                )}
                actions={
                    <button
                        onClick={handleSave}
                        disabled={!isDirty || saving}
                        className="btn-primary cursor-pointer disabled:cursor-not-allowed"
                    >
                        {saving ? <Activity size={15} className="animate-spin" /> : <Save size={15} />}
                        Save branding
                    </button>
                }
            />

            <div className="grid grid-cols-12 gap-6">
                {/* Logo */}
                <Section
                    span="md:col-span-6"
                    icon={<ImageIcon size={16} />}
                    title="Hospital logo"
                    desc="Shown in the sidebar, login screen, and printed documents. PNG/JPG/SVG, max 600 KB."
                >
                    <ImageDrop
                        value={draft.logo_data_url}
                        onChange={(v) => set('logo_data_url', v)}
                        onClear={() => set('logo_data_url', null)}
                        maxBytes={MAX_LOGO_BYTES}
                        aspect="square"
                        emptyHint="No custom logo — the MediFleet mark is shown."
                    />
                </Section>

                {/* Background */}
                <Section
                    span="md:col-span-6"
                    icon={<ImageIcon size={16} />}
                    title="Sign-in background"
                    desc="Overlays the brand panel on the Login screen. Use a calm, low-contrast photo (max 900 KB)."
                >
                    <ImageDrop
                        value={draft.background_data_url}
                        onChange={(v) => set('background_data_url', v)}
                        onClear={() => set('background_data_url', null)}
                        maxBytes={MAX_BG_BYTES}
                        aspect="wide"
                        emptyHint="No background — the cyan/teal gradient is used."
                    />
                </Section>

                {/* Brand colours */}
                <Section
                    span="md:col-span-6"
                    icon={<Palette size={16} />}
                    title="Brand colours"
                    desc="Optional overrides. Leave blank to use the MediFleet defaults."
                >
                    <div className="space-y-4">
                        <ColorField
                            label="Primary"
                            value={draft.brand_primary || ''}
                            placeholder="#0891b2 (cyan)"
                            onChange={(v) => set('brand_primary', v)}
                        />
                        <ColorField
                            label="Accent"
                            value={draft.brand_accent || ''}
                            placeholder="#10b981 (emerald)"
                            onChange={(v) => set('brand_accent', v)}
                        />
                        <p className="text-xs text-ink-500 leading-relaxed">
                            Tip: pick hues that pass a 4.5:1 contrast ratio against white. The defaults
                            already do.
                        </p>
                    </div>
                </Section>

                {/* Print templates */}
                <Section
                    span="md:col-span-6"
                    icon={<Printer size={16} />}
                    title="Print templates"
                    desc="Header, footer, and layout style for invoices, lab reports, prescriptions, and discharge summaries."
                >
                    <div className="space-y-4">
                        <div>
                            <label className="label">Header text</label>
                            <input
                                className="input"
                                value={draft.print_templates?.header_text || ''}
                                onChange={(e) => setTemplate('header_text', e.target.value)}
                                placeholder="e.g. Mayo Clinic Nairobi · Outpatient Department"
                            />
                        </div>
                        <div>
                            <label className="label">Footer text</label>
                            <input
                                className="input"
                                value={draft.print_templates?.footer_text || ''}
                                onChange={(e) => setTemplate('footer_text', e.target.value)}
                                placeholder="e.g. P.O. Box 12345 · +254 700 123456 · billing@example.com"
                            />
                        </div>
                        <div>
                            <label className="label">Layout style</label>
                            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                                {TEMPLATE_OPTIONS.map((opt) => {
                                    const active = (draft.print_templates?.primary_template || 'modern') === opt.key;
                                    return (
                                        <button
                                            key={opt.key}
                                            type="button"
                                            onClick={() => setTemplate('primary_template', opt.key)}
                                            className={`text-left p-3 rounded-xl border transition-all cursor-pointer ${
                                                active
                                                    ? 'border-brand-400 bg-brand-50 ring-2 ring-brand-200'
                                                    : 'border-ink-200 bg-white hover:border-brand-200 hover:bg-brand-50/30'
                                            }`}
                                        >
                                            <div className="flex items-center justify-between">
                                                <span className="text-sm font-semibold text-ink-900">{opt.label}</span>
                                                {active && <CheckCircle2 size={14} className="text-brand-600" />}
                                            </div>
                                            <p className="mt-1 text-xs text-ink-500">{opt.hint}</p>
                                        </button>
                                    );
                                })}
                            </div>
                        </div>
                        <label className="flex items-center gap-3 cursor-pointer select-none">
                            <input
                                type="checkbox"
                                checked={draft.print_templates?.show_logo !== false}
                                onChange={(e) => setTemplate('show_logo', e.target.checked)}
                                className="sr-only peer"
                            />
                            <span className="w-11 h-6 bg-ink-200 rounded-full peer peer-checked:bg-brand-500 transition relative after:absolute after:left-0.5 after:top-0.5 after:bg-white after:rounded-full after:w-5 after:h-5 after:transition peer-checked:after:translate-x-5" />
                            <span className="text-sm font-medium text-ink-700">Print my logo on documents</span>
                        </label>
                    </div>
                </Section>

                {/* Preview */}
                <Section
                    span="md:col-span-12"
                    icon={<Eye size={16} />}
                    title="Preview"
                    desc="How the new branding lands on the sign-in screen."
                >
                    <PreviewCard
                        logo={draft.logo_data_url}
                        background={draft.background_data_url}
                        primary={draft.brand_primary}
                        accent={draft.brand_accent}
                    />
                </Section>
            </div>
        </div>
    );
}

/* ─────────────────────────────────────────────────────────────────────────── */
/*  Subcomponents                                                              */
/* ─────────────────────────────────────────────────────────────────────────── */

function Section({ span, icon, title, desc, children }) {
    return (
        <section className={`col-span-12 ${span} card overflow-hidden`}>
            <div className="px-5 py-3 border-b border-ink-100 bg-ink-50/40 flex items-center gap-2">
                <span className="text-brand-600">{icon}</span>
                <h2 className="text-sm font-semibold text-ink-900 tracking-tight">{title}</h2>
            </div>
            <div className="p-5 space-y-4">
                <p className="text-xs text-ink-500 leading-relaxed">{desc}</p>
                {children}
            </div>
        </section>
    );
}

function ImageDrop({ value, onChange, onClear, maxBytes, aspect = 'wide', emptyHint }) {
    const inputRef = useRef(null);
    const [error, setError] = useState(null);

    const handleFile = async (file) => {
        if (!file) return;
        setError(null);
        if (file.size > maxBytes * 1.5) {
            setError(`Image is ${Math.round(file.size / 1024)} KB — please compress to under ${Math.round(maxBytes / 1024)} KB.`);
            return;
        }
        const reader = new FileReader();
        reader.onload = () => {
            const dataUrl = reader.result;
            if (typeof dataUrl !== 'string' || !dataUrl.startsWith('data:image/')) {
                setError('Unsupported file type. Use PNG, JPG, or SVG.');
                return;
            }
            if (dataUrl.length > maxBytes) {
                setError(`Encoded image is ${Math.round(dataUrl.length / 1024)} KB — compress further or pick a smaller image.`);
                return;
            }
            onChange(dataUrl);
        };
        reader.onerror = () => setError('Failed to read the file.');
        reader.readAsDataURL(file);
    };

    const aspectClass = aspect === 'square' ? 'aspect-square' : 'aspect-[16/9]';

    return (
        <div className="space-y-3">
            <div className={`relative ${aspectClass} rounded-2xl border border-dashed border-ink-300 bg-ink-50/40 overflow-hidden flex items-center justify-center group`}>
                {value ? (
                    <>
                        <img src={value} alt="Preview" className="absolute inset-0 w-full h-full object-contain bg-white" />
                        <div className="absolute inset-0 bg-ink-900/0 group-hover:bg-ink-900/40 transition-colors flex items-center justify-center gap-2 opacity-0 group-hover:opacity-100">
                            <button
                                type="button"
                                onClick={() => inputRef.current?.click()}
                                className="px-3 py-2 rounded-lg bg-white text-ink-800 text-xs font-semibold shadow-soft hover:bg-brand-50 cursor-pointer flex items-center gap-1.5"
                            >
                                <Upload size={13} /> Replace
                            </button>
                            <button
                                type="button"
                                onClick={onClear}
                                className="px-3 py-2 rounded-lg bg-rose-600 text-white text-xs font-semibold shadow-soft hover:bg-rose-700 cursor-pointer flex items-center gap-1.5"
                            >
                                <Trash2 size={13} /> Remove
                            </button>
                        </div>
                    </>
                ) : (
                    <button
                        type="button"
                        onClick={() => inputRef.current?.click()}
                        className="flex flex-col items-center justify-center w-full h-full text-ink-500 hover:text-brand-700 hover:bg-brand-50/30 transition-colors cursor-pointer"
                    >
                        <Upload size={22} className="mb-2" />
                        <span className="text-sm font-semibold">Click to upload</span>
                        <span className="text-xs mt-1">{emptyHint}</span>
                    </button>
                )}
                <input
                    ref={inputRef}
                    type="file"
                    accept="image/png,image/jpeg,image/jpg,image/svg+xml,image/webp"
                    className="hidden"
                    onChange={(e) => handleFile(e.target.files?.[0])}
                />
            </div>
            {error && (
                <p className="text-xs text-rose-600 flex items-start gap-1.5">
                    <AlertTriangle size={13} className="shrink-0 mt-0.5" /> {error}
                </p>
            )}
        </div>
    );
}

function ColorField({ label, value, placeholder, onChange }) {
    const isValid = !value || /^#[0-9a-fA-F]{3,8}$/.test(value);
    return (
        <div className="flex items-center gap-3">
            <div
                className="w-10 h-10 rounded-xl border border-ink-200 shadow-soft shrink-0"
                style={{ backgroundColor: isValid && value ? value : '#f1f5f9' }}
            />
            <div className="flex-1">
                <label className="label">{label}</label>
                <input
                    type="text"
                    className={`input ${!isValid ? 'border-rose-400 focus:border-rose-500 focus:ring-rose-500/20' : ''}`}
                    value={value}
                    onChange={(e) => onChange(e.target.value.trim())}
                    placeholder={placeholder}
                    spellCheck={false}
                />
            </div>
            <input
                type="color"
                aria-label={`${label} color picker`}
                value={isValid && value ? (value.length === 7 ? value : '#06b6d4') : '#06b6d4'}
                onChange={(e) => onChange(e.target.value)}
                className="w-10 h-10 rounded-xl border border-ink-200 cursor-pointer bg-white"
            />
        </div>
    );
}

function PreviewCard({ logo, background, primary, accent }) {
    const tenantName = localStorage.getItem('hms_tenant_name') || 'Your Hospital';
    return (
        <div className="rounded-2xl border border-ink-200 overflow-hidden shadow-soft bg-white">
            <div className="grid lg:grid-cols-5">
                {/* Left brand panel */}
                <div
                    className="relative lg:col-span-2 min-h-[280px] bg-brand-gradient text-white overflow-hidden"
                    style={
                        primary
                            ? { backgroundImage: `linear-gradient(135deg, ${primary} 0%, ${accent || primary} 100%)` }
                            : undefined
                    }
                >
                    {background && (
                        <div
                            className="absolute inset-0 bg-cover bg-center opacity-40 mix-blend-overlay"
                            style={{ backgroundImage: `url("${background}")` }}
                        />
                    )}
                    <div className="absolute inset-0 bg-aurora opacity-70" />
                    <div className="relative p-6 flex flex-col justify-between h-full">
                        <TenantLogo
                            src={logo}
                            fallbackLabel={tenantName}
                            sublabel="Hospital workspace"
                            size={36}
                            tone="mono-light"
                        />
                        <div>
                            <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-white/70">Tagline</p>
                            <p className="mt-1 text-xl font-semibold leading-tight">Care, coordinated.</p>
                        </div>
                    </div>
                </div>
                {/* Right form preview */}
                <div className="lg:col-span-3 p-6 space-y-3">
                    <div>
                        <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-ink-500">Welcome back</p>
                        <h3 className="mt-1 text-xl font-semibold text-ink-900 tracking-tight">Sign in to {tenantName}</h3>
                    </div>
                    <div className="space-y-2 max-w-md">
                        <div className="h-9 rounded-lg bg-ink-100" />
                        <div className="h-9 rounded-lg bg-ink-100" />
                        <button
                            type="button"
                            disabled
                            className="w-full h-10 rounded-lg text-white font-semibold text-sm shadow-soft"
                            style={{
                                background: primary
                                    ? `linear-gradient(135deg, ${primary}, ${accent || primary})`
                                    : 'linear-gradient(135deg, #0891b2, #10b981)',
                            }}
                        >
                            Sign in
                        </button>
                    </div>
                    <div className="flex items-center gap-3 pt-2">
                        <Logo variant="mark" size={22} />
                        <span className="text-2xs text-ink-500 uppercase tracking-[0.14em]">
                            Powered by MediFleet
                        </span>
                    </div>
                </div>
            </div>
        </div>
    );
}
