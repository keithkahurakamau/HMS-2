import React, { useState } from 'react';
import { Send, User, Mail, Building2, MessageSquare } from 'lucide-react';
import toast from 'react-hot-toast';
import { apiClient } from '../api/client';

/**
 * ContactForm — public landing-page lead capture.
 *
 * Posts to /api/public/contact, which emails the support inbox with Reply-To
 * set to the visitor so the team replies straight to the prospect. Includes a
 * hidden honeypot ("website") to drop bots. Pairs with ContactStrip (which
 * offers phone / WhatsApp / mailto for people who prefer those).
 */
export default function ContactForm() {
    const [form, setForm] = useState({ name: '', email: '', company: '', message: '', department: 'general', website: '' });
    const [submitting, setSubmitting] = useState(false);
    const [sent, setSent] = useState(false);

    const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!form.name.trim() || !form.email.trim() || !form.message.trim()) {
            return toast.error('Please fill in your name, email and message.');
        }
        setSubmitting(true);
        try {
            await apiClient.post('/public/contact', form);
            setSent(true);
            toast.success("Thanks — we'll be in touch shortly.");
        } catch (err) {
            const detail = err.response?.data?.detail;
            toast.error(Array.isArray(detail) ? (detail[0]?.msg || 'Could not send.') : (detail || 'Could not send your message. Please try again.'));
        } finally {
            setSubmitting(false);
        }
    };

    if (sent) {
        return (
            <div className="glass-card rounded-2xl p-8 text-center">
                <div className="size-12 mx-auto rounded-full bg-teal-50 text-teal-600 ring-1 ring-teal-100 flex items-center justify-center">
                    <Send size={20} />
                </div>
                <h3 className="mt-4 text-lg font-semibold text-ink-900">Message sent</h3>
                <p className="mt-1.5 text-sm text-ink-600">
                    Thanks for reaching out — the MediFleet team will reply to <strong className="text-ink-800">{form.email}</strong> within one business day.
                </p>
            </div>
        );
    }

    return (
        <form onSubmit={handleSubmit} className="glass-card rounded-2xl p-6 sm:p-7 space-y-4">
            {/* Honeypot — visually hidden; real users never fill it. */}
            <input
                type="text" tabIndex={-1} autoComplete="off" aria-hidden="true"
                value={form.website} onChange={set('website')}
                className="hidden" name="website"
            />

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                    <label htmlFor="cf-name" className="label">Your name</label>
                    <div className="relative">
                        <User size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-400" />
                        <input id="cf-name" type="text" required value={form.name} onChange={set('name')}
                            className="input pl-9" placeholder="Jane Doe" maxLength={120} />
                    </div>
                </div>
                <div>
                    <label htmlFor="cf-email" className="label">Email</label>
                    <div className="relative">
                        <Mail size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-400" />
                        <input id="cf-email" type="email" required value={form.email} onChange={set('email')}
                            className="input pl-9" placeholder="you@hospital.co.ke" maxLength={254} />
                    </div>
                </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                    <label htmlFor="cf-company" className="label">Hospital / organization <span className="text-ink-400 font-normal">(optional)</span></label>
                    <div className="relative">
                        <Building2 size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-400" />
                        <input id="cf-company" type="text" value={form.company} onChange={set('company')}
                            className="input pl-9" placeholder="Nairobi Community Hospital" maxLength={160} />
                    </div>
                </div>
                <div>
                    <label htmlFor="cf-department" className="label">What's this about?</label>
                    <select id="cf-department" value={form.department} onChange={set('department')} className="input">
                        <option value="general">General enquiry / Sales</option>
                        <option value="billing">Billing &amp; payments</option>
                        <option value="technical">Technical support</option>
                    </select>
                </div>
            </div>

            <div>
                <label htmlFor="cf-message" className="label">How can we help?</label>
                <div className="relative">
                    <MessageSquare size={16} className="absolute left-3 top-3 text-ink-400" />
                    <textarea id="cf-message" required rows={4} value={form.message} onChange={set('message')}
                        className="input pl-9 resize-y" placeholder="Tell us a little about your clinic and what you're looking for…" maxLength={5000} />
                </div>
            </div>

            <button type="submit" disabled={submitting} className="btn-primary w-full py-3 inline-flex items-center justify-center gap-2">
                {submitting ? 'Sending…' : (<><Send size={16} /> Send message</>)}
            </button>
            <p className="helper text-center">We reply within one business day. Prefer to talk now? Use the call or WhatsApp options below.</p>
        </form>
    );
}
