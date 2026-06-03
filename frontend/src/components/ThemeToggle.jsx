import React from 'react';
import { Sun, Moon, Monitor } from 'lucide-react';
import { useTheme } from '../context/ThemeContext';

const OPTIONS = [
    { value: 'light', label: 'Light', icon: Sun },
    { value: 'dark', label: 'Dark', icon: Moon },
    { value: 'system', label: 'System', icon: Monitor },
];

// `scope` selects which independent theme this control drives:
//   • 'tenant' (default) → the client workspace theme (hms_theme)
//   • 'admin'            → the platform back-office theme (hms_admin_theme),
//                          independent of any tenant client's choice.
export default function ThemeToggle({ compact = false, scope = 'tenant' }) {
    const ctx = useTheme();
    const isAdmin = scope === 'admin';
    const theme = isAdmin ? ctx.adminTheme : ctx.theme;
    const resolved = isAdmin ? ctx.resolvedAdmin : ctx.resolved;
    const setTheme = isAdmin ? ctx.setAdminTheme : ctx.setTheme;

    if (compact) {
        // Single-button toggle for tight headers. Uses the resolved value so the
        // icon is correct even when the scope is in 'system' mode.
        const next = resolved === 'dark' ? 'light' : 'dark';
        const Icon = resolved === 'dark' ? Sun : Moon;
        return (
            <button
                type="button"
                onClick={() => setTheme(next)}
                aria-label={`Switch to ${next} theme`}
                className="p-2 text-slate-500 hover:text-slate-800 dark:text-slate-300 dark:hover:text-white rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
            >
                <Icon size={20} aria-hidden="true" />
            </button>
        );
    }

    return (
        <div role="radiogroup" aria-label="Theme" className="inline-flex items-center bg-slate-100 dark:bg-slate-800 rounded-lg p-1 gap-1">
            {OPTIONS.map(({ value, label, icon: Icon }) => {
                const active = theme === value;
                return (
                    <button
                        key={value}
                        role="radio"
                        aria-checked={active}
                        type="button"
                        onClick={() => setTheme(value)}
                        className={`px-2.5 py-1 rounded text-xs font-bold flex items-center gap-1.5 transition-colors ${
                            active
                                ? 'bg-white dark:bg-slate-900 text-slate-900 dark:text-white shadow-sm'
                                : 'text-slate-500 hover:text-slate-800 dark:hover:text-white'
                        }`}
                    >
                        <Icon size={13} aria-hidden="true" />
                        {label}
                    </button>
                );
            })}
        </div>
    );
}
