import React from 'react';
import Logo from './Logo';

/**
 * Footer shared by the public pages (Landing, Demo).
 *
 * Carries the Nova-Habitat Technologies attribution, so the parent-company
 * line lives in one place rather than being copy-pasted per page, the two
 * footers had already drifted apart in their link sets before this.
 *
 * `children` are the page's own quick links, which differ per page.
 */

export const PARENT_COMPANY = 'Nova-Habitat Technologies';
export const PARENT_COMPANY_URL = 'https://www.novahabitat.tech';

export default function PublicFooter({ children }) {
    return (
        <footer className="border-t border-[#b2f0f0] bg-[#f2fdfd]">
            <div className="max-w-7xl mx-auto px-5 sm:px-6 py-10 flex flex-col md:flex-row items-center justify-between gap-5">
                <div className="flex flex-col items-center md:items-start gap-2">
                    <Logo variant="full" size={28} />
                    <p className="text-2xs text-ink-500 uppercase tracking-[0.18em]">
                        A product of{' '}
                        <a
                            href={PARENT_COMPANY_URL}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="font-semibold text-[#015050] hover:text-[#00d4d4] transition-colors"
                        >
                            {PARENT_COMPANY}
                        </a>
                    </p>
                </div>

                <p className="text-xs text-ink-500 uppercase tracking-[0.18em] text-center">
                    {/* react-doctor-disable-next-line react-doctor/rendering-hydration-mismatch-time */}
                    &copy; {new Date().getFullYear()} MediFleet · Clinical-grade workspace
                </p>

                <div className="flex items-center gap-4 text-xs font-semibold text-[#015050]">
                    {children}
                </div>
            </div>
        </footer>
    );
}
