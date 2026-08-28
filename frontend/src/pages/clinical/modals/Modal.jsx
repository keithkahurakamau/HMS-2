import React from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';

/**
 * Shared modal shell for the DoctorV2 clinical desk, portaled to <body> so it
 * escapes the workspace card's stacking context and always sits above the queue
 * bar and page chrome. Mirrors the shell in ClinicalExtrasPanel so every modal
 * on the desk looks and behaves identically.
 *
 * `size`: 'sm' | 'md' | 'lg' | 'xl' controls max width.
 */
const WIDTHS = { sm: 'max-w-md', md: 'max-w-lg', lg: 'max-w-2xl', xl: 'max-w-4xl' };

export default function Modal({ title, icon: Icon, onClose, children, footer, size = 'md' }) {
    return createPortal(
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/50 backdrop-blur-sm p-4"
            onClick={onClose} role="presentation">
            <div className={`bg-white dark:bg-ink-900 rounded-2xl shadow-overlay w-full ${WIDTHS[size] || WIDTHS.md} max-h-[90vh] flex flex-col`}
                onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-label={title}>
                <div className="flex items-center justify-between p-4 border-b border-ink-100 dark:border-ink-800">
                    <h3 className="text-sm font-semibold text-ink-900 dark:text-white flex items-center gap-2">
                        {Icon && <Icon size={16} className="text-brand-500" />} {title}
                    </h3>
                    <button type="button" onClick={onClose} aria-label="Close"
                        className="p-1.5 rounded-lg text-ink-400 hover:bg-ink-100 dark:hover:bg-ink-800"><X size={16} /></button>
                </div>
                <div className="flex-1 overflow-y-auto p-5 space-y-4 custom-scrollbar">{children}</div>
                {footer && <div className="p-4 border-t border-ink-100 dark:border-ink-800 flex justify-end gap-2">{footer}</div>}
            </div>
        </div>,
        document.body,
    );
}
