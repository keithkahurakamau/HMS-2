import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { apiClient } from '../api/client';
import toast from 'react-hot-toast';
import { ArrowLeft, Mail, ShieldCheck, ShieldAlert } from 'lucide-react';

export default function ForgotPassword() {
    const [email, setEmail] = useState('');
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [submitted, setSubmitted] = useState(false);
    const [devToken, setDevToken] = useState(null);
    const navigate = useNavigate();

    const tenantName = localStorage.getItem('hms_tenant_name') || 'MediFleet';

    const handleSubmit = async (e) => {
        e.preventDefault();
        setIsSubmitting(true);
        try {
            const res = await apiClient.post('/auth/forgot-password', { email });
            setSubmitted(true);
            if (res.data?.dev_token) setDevToken(res.data.dev_token);
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Could not process request.');
        } finally {
            setIsSubmitting(false);
        }
    };

    return (
        <div className="min-h-screen bg-ink-50 flex flex-col justify-center py-12 sm:px-6 lg:px-8 bg-mesh">
            <div className="sm:mx-auto sm:w-full sm:max-w-md text-center">
                <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-brand-gradient shadow-glow">
                    <ShieldCheck size={28} className="text-white" />
                </div>
                <h2 className="mt-6 text-3xl font-semibold text-ink-900 tracking-tight">{tenantName}</h2>
                <p className="mt-2 text-sm text-ink-500">Reset your account password</p>
            </div>

            <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md animate-slide-up">
                <div className="card p-8">
                    {submitted ? (
                        <div className="text-center space-y-5">
                            <div className="w-14 h-14 mx-auto rounded-2xl bg-accent-50 ring-1 ring-accent-100 flex items-center justify-center">
                                <ShieldCheck size={26} className="text-accent-600" />
                            </div>
                            <div>
                                <h3 className="text-lg font-semibold text-ink-900">Check your email</h3>
                                <p className="text-sm text-ink-500 mt-1.5 leading-relaxed">
                                    If an account exists for <strong className="text-ink-700">{email}</strong>, a password reset link has been sent. The link expires in 60 minutes.
                                </p>
                            </div>

                            {devToken && (
                                <div className="text-left bg-amber-50 border border-amber-200 rounded-xl p-3.5 text-xs text-amber-900">
                                    <p className="font-semibold uppercase tracking-[0.14em] mb-1.5 text-2xs">Dev mode &mdash; reset token</p>
                                    <code className="block break-all font-mono text-xs bg-white/60 rounded p-2 ring-1 ring-amber-200">{devToken}</code>
                                    <button
                                        type="button"
                                        onClick={() => navigate(`/reset-password?token=${devToken}`)}
                                        className="mt-2.5 w-full py-2 bg-amber-600 hover:bg-amber-700 text-white rounded-lg text-xs font-semibold transition-colors"
                                    >
                                        Use this token &rarr;
                                    </button>
                                </div>
                            )}

                            <Link to="/login" className="inline-flex items-center gap-1.5 text-sm text-brand-600 hover:text-brand-700 font-semibold">
                                <ArrowLeft size={14} /> Back to sign in
                            </Link>
                        </div>
                    ) : (
                        <form onSubmit={handleSubmit} className="space-y-5">
                            <div>
                                <label htmlFor="reset-email" className="label">Email address</label>
                                <div className="relative">
                                    <Mail size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-400" />
                                    <input
                                        id="reset-email"
                                        type="email"
                                        required
                                        autoComplete="email"
                                        value={email}
                                        onChange={(e) => setEmail(e.target.value)}
                                        className="input pl-9"
                                        placeholder="you@example.com"
                                    />
                                </div>
                                <p className="helper">
                                    We'll send a single-use link valid for 60 minutes. For security, the response is the same whether or not the email is registered.
                                </p>
                            </div>

                            <button type="submit" disabled={isSubmitting} className="btn-primary w-full py-3">
                                {isSubmitting ? 'Sending…' : 'Send reset link'}
                            </button>

                            <div className="flex items-center justify-center gap-2 text-xs text-ink-500 pt-1">
                                <ShieldAlert size={14} className="text-brand-500" />
                                Single-use, signed token &mdash; never shared via email body
                            </div>

                            <div className="text-center pt-2">
                                <Link to="/login" className="inline-flex items-center gap-1.5 text-sm text-ink-600 hover:text-ink-900 font-medium">
                                    <ArrowLeft size={14} /> Back to sign in
                                </Link>
                            </div>
                        </form>
                    )}
                </div>
            </div>
        </div>
    );
}
