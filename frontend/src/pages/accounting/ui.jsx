/* Shared presentational primitives for the accounting feature tabs.
 * These mirror the inline helpers in ../Accounting.jsx so the budget,
 * notes, and bulk-allocation views render with identical styling. */
import React from 'react';
import { X, Plus } from 'lucide-react';
// formatAmount / todayISO moved to ./format (non-component file) so this file
// exports only components — keeps Fast Refresh working.

export function SectionHeader({ title, subtitle, onNew, disabled, disabledMsg, newLabel = 'New' }) {
    return (
        <div className="flex items-start justify-between">
            <div>
                <h3 className="text-lg font-semibold text-ink-900">{title}</h3>
                {subtitle && <p className="text-sm text-ink-600 mt-1">{subtitle}</p>}
            </div>
            {onNew && (
                <button onClick={onNew} disabled={disabled} title={disabled ? disabledMsg : undefined}
                        className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-brand-600 text-white text-sm font-medium hover:bg-brand-700 disabled:opacity-60 disabled:cursor-not-allowed">
                    <Plus size={16} /> {newLabel}
                </button>
            )}
        </div>
    );
}

export function DataCard({ loading, empty, emptyMsg, children }) {
    return (
        <div className="bg-white border border-ink-200/70 rounded-2xl shadow-soft overflow-hidden">
            {loading ? (
                <div className="p-6 text-sm text-ink-500">Loading...</div>
            ) : empty ? (
                <div className="p-6 text-sm text-ink-500">{emptyMsg}</div>
            ) : children}
        </div>
    );
}

export function ModalShell({ title, onClose, wide, children }) {
    return (
        <div className="fixed inset-0 bg-ink-900/40 backdrop-blur-sm flex items-center justify-center z-50 p-4">
            <div className={'bg-white rounded-2xl shadow-elevated w-full ' + (wide ? 'max-w-3xl' : 'max-w-md')}>
                <div className="flex items-center justify-between p-4 border-b border-ink-100">
                    <h3 className="text-sm font-semibold text-ink-900">{title}</h3>
                    <button onClick={onClose} className="text-ink-400 hover:text-ink-700">
                        <X size={18} />
                    </button>
                </div>
                <div className="p-5">{children}</div>
            </div>
        </div>
    );
}

export function ModalActions({ onClose, onSubmit, saving, submitLabel = 'Save' }) {
    return (
        <div className="flex justify-end gap-2 mt-5 pt-4 border-t border-ink-100">
            <button onClick={onClose}
                    className="px-3 py-2 rounded-lg border border-ink-200 text-sm font-medium hover:bg-ink-50">
                Cancel
            </button>
            <button onClick={onSubmit} disabled={saving}
                    className="px-3 py-2 rounded-lg bg-brand-600 text-white text-sm font-medium hover:bg-brand-700 disabled:opacity-60">
                {saving ? 'Saving...' : submitLabel}
            </button>
        </div>
    );
}

export function Field({ label, children }) {
    return (
        <label className="block">
            <span className="block text-xs font-medium text-ink-600 mb-1">{label}</span>
            {children}
        </label>
    );
}
