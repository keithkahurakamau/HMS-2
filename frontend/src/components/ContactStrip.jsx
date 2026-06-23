import React from 'react';
import { Phone, Mail, MessageCircle } from 'lucide-react';

/**
 * ContactStrip - three-way contact card row (phone / email / WhatsApp).
 *
 * Used on the Landing and Portal pages so a visitor stuck on a step has
 * three immediate paths to a human. WhatsApp uses the wa.me deep-link so
 * it opens the app on mobile and the web client on desktop.
 *
 * To update the support number / email, edit SUPPORT_CONTACT below; both
 * pages pull from this single source.
 */
const SUPPORT_CONTACT = {
    phone: '0706542442',
    phoneE164: '+254706542442',
    email: 'support@medifleet.app',
    // wa.me requires the number without the leading '+'.
    whatsappPath: '254706542442',
};

export default function ContactStrip({ heading = "Need a hand?" }) {
    return (
        <section className="relative py-14 sm:py-20">
            <div className="max-w-5xl mx-auto px-6">
                <div className="text-center mb-10">
                    <span className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white ring-1 ring-brand-200 text-2xs font-semibold uppercase tracking-[0.16em] text-brand-700">
                        Support
                    </span>
                    <h2 className="mt-4 text-2xl sm:text-3xl font-semibold tracking-tight text-ink-900">{heading}</h2>
                    <p className="mt-2 text-sm text-ink-600 max-w-xl mx-auto">
                        The MediFleet support team is reachable in three ways. Pick the one that fits the moment.
                    </p>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                    <ContactCard
                        href={`tel:${SUPPORT_CONTACT.phoneE164}`}
                        icon={<Phone size={20} />}
                        tone="brand"
                        label="Call us"
                        value={SUPPORT_CONTACT.phone}
                        hint="Mon to Sat, 8 am to 8 pm EAT"
                    />
                    <ContactCard
                        href={`https://wa.me/${SUPPORT_CONTACT.whatsappPath}`}
                        icon={<MessageCircle size={20} />}
                        tone="accent"
                        label="WhatsApp"
                        value={SUPPORT_CONTACT.phone}
                        hint="Fastest path on mobile"
                        external
                    />
                    <ContactCard
                        href={`mailto:${SUPPORT_CONTACT.email}`}
                        icon={<Mail size={20} />}
                        tone="teal"
                        label="Email"
                        value={SUPPORT_CONTACT.email}
                        hint="Replies within one business day"
                    />
                </div>

                {/* Email a specific team, routes to the matching desk */}
                <div className="mt-8">
                    <p className="text-center text-2xs font-semibold uppercase tracking-[0.16em] text-ink-500 mb-3">Email a specific team</p>
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                        {[
                            { label: 'Support', email: 'support@medifleet.app', hint: 'Accounts & general help' },
                            { label: 'Billing', email: 'finance@medifleet.app', hint: 'Invoices & payments' },
                            { label: 'Technical', email: 'technical@medifleet.app', hint: 'Bugs & integrations' },
                        ].map((t) => (
                            <a
                                key={t.email}
                                href={`mailto:${t.email}`}
                                className="group flex items-center gap-3 rounded-xl bg-white ring-1 ring-ink-200 hover:ring-brand-300 px-4 py-3 transition-all"
                            >
                                <Mail size={16} className="text-brand-600 shrink-0" />
                                <span className="min-w-0">
                                    <span className="block text-sm font-semibold text-ink-900 group-hover:text-brand-700 transition-colors">{t.label}</span>
                                    <span className="block text-2xs text-ink-500 truncate">{t.email}</span>
                                </span>
                            </a>
                        ))}
                    </div>
                </div>
            </div>
        </section>
    );
}

function ContactCard({ href, icon, tone, label, value, hint, external }) {
    const ring =
        tone === 'brand'  ? 'bg-brand-50 text-brand-700 ring-brand-100'
      : tone === 'accent' ? 'bg-accent-50 text-accent-700 ring-accent-100'
                          : 'bg-teal-50 text-teal-700 ring-teal-100';
    return (
        <a
            href={href}
            {...(external ? { target: '_blank', rel: 'noopener noreferrer' } : {})}
            className="group relative glass-card rounded-2xl p-5 hover:ring-brand-300 transition-all cursor-pointer overflow-hidden"
        >
            {/* Subtle gradient reveal on hover */}
            <div className="pointer-events-none absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity bg-gradient-to-br from-brand-500/0 via-brand-500/[0.04] to-teal-500/[0.06]" />
            <div className="relative flex items-start gap-3">
                <div className={`size-11 rounded-xl ring-1 ring-inset flex items-center justify-center shrink-0 group-hover:scale-105 transition-transform ${ring}`}>
                    {icon}
                </div>
                <div className="min-w-0">
                    <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-ink-500">{label}</p>
                    <p className="mt-0.5 text-sm font-semibold text-ink-900 truncate group-hover:text-brand-700 transition-colors">{value}</p>
                    <p className="mt-1 text-xs text-ink-500">{hint}</p>
                </div>
            </div>
        </a>
    );
}
