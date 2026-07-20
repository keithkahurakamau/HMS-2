import { Info, AlertCircle, AlertTriangle, CheckCircle2 } from 'lucide-react';

// Shared between NotificationBell.jsx (the inbox) and NotificationToast.jsx
// (the live sneak-peek popup) so both render the same category exactly the
// same way — one icon/colour mapping, not two that can drift apart.
export const NOTIFICATION_CATEGORY_ICONS = {
    info: Info,
    success: CheckCircle2,
    warning: AlertTriangle,
    critical: AlertCircle,
};

// Map each category to a tinted icon container — the rail/icon colour is the
// only place categories should differ. Cards themselves stay neutral so the
// overall inbox doesn't feel like a Christmas tree.
export const NOTIFICATION_CATEGORY_STYLE = {
    info:     { ring: 'bg-blue-50 ring-blue-100 text-blue-600',
                rail: 'bg-blue-500',     label: 'text-blue-700' },
    success:  { ring: 'bg-accent-50 ring-accent-100 text-accent-600',
                rail: 'bg-accent-500',   label: 'text-accent-700' },
    warning:  { ring: 'bg-amber-50 ring-amber-100 text-amber-600',
                rail: 'bg-amber-500',    label: 'text-amber-700' },
    critical: { ring: 'bg-rose-50 ring-rose-100 text-rose-600',
                rail: 'bg-rose-500',     label: 'text-rose-700' },
};
