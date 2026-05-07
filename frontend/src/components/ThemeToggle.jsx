import React from 'react';
import { Sun, Moon, Monitor } from 'lucide-react';
import { useTheme } from '../context/ThemeContext';

const OPTIONS = [
    { value: 'light', label: 'Light', icon: Sun },
    { value: 'dark', label: 'Dark', icon: Moon },
    { value: 'system', label: 'System', icon: Monitor },
];

export default function ThemeToggle({ compact = false }) {
    const { theme, setTheme } = useTheme();

    if (compact) {
        // Single-button toggle for tight headers.
        const next = theme === 'dark' ? 'light' : 'dark';
        const Icon = theme === 'dark' ? Sun : Moon;
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
