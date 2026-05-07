import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { apiClient } from '../api/client';
import toast from 'react-hot-toast';
import { Activity, ArrowLeft, Mail, ShieldCheck } from 'lucide-react';

export default function ForgotPassword() {
    const [email, setEmail] = useState('');
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [submitted, setSubmitted] = useState(false);
    const [devToken, setDevToken] = useState(null);
    const navigate = useNavigate();

    const tenantName = localStorage.getItem('hms_tenant_name') || 'HMS Enterprise';

    const handleSubmit = async (e) => {
        e.preventDefault();
        setIsSubmitting(true);
        try {
            const res = await apiClient.post('/auth/forgot-password', { email });
            setSubmitted(true);
            // dev_token only present in non-production. Surface it so testers can
            // walk the flow end-to-end without SMTP wired up.
            if (res.data?.dev_token) {
                setDevToken(res.data.dev_token);
            }
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Could not process request.');
        } finally {
            setIsSubmitting(false);
        }
    };

    return (
        <div className="min-h-screen bg-slate-50 flex flex-col justify-center py-12 sm:px-6 lg:px-8">
            <div className="sm:mx-auto sm:w-full sm:max-w-md">
                <div className="flex justify-center text-brand-600">
                    <Activity size={48} strokeWidth={1.5} />
                </div>
                <h2 className="mt-6 text-center text-3xl font-extrabold text-slate-900">{tenantName}</h2>
                <p className="mt-2 text-center text-sm text-slate-600">Reset your account password</p>
            </div>

            <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
                <div className="bg-white py-8 px-4 shadow-soft sm:rounded-xl sm:px-10 border border-slate-100">
                    {submitted ? (
                        <div className="text-center space-y-4">
                            <div className="w-16 h-16 mx-auto rounded-2xl bg-green-50 border border-green-200 flex items-center justify-center">
                                <ShieldCheck size={32} className="text-green-600" />
                            </div>
                            <h3 className="text-lg font-bold text-slate-900">Check your email</h3>
                            <p className="text-sm text-slate-600">
                                If an account exists for <strong>{email}</strong>, a password reset link has been sent. The link expires in 60 minutes.
                            </p>

                            {devToken && (
                                <div className="text-left bg-amber-50 border border-amber-200 rounded-lg p-3 text-xs text-amber-900">
                                    <p className="font-bold uppercase tracking-wider mb-1">Dev mode — reset token</p>
                                    <code className="break-all font-mono">{devToken}</code>
                                    <button
                                        type="button"
                                        onClick={() => navigate(`/reset-password?token=${devToken}`)}
                                        className="mt-2 w-full py-2 bg-amber-600 hover:bg-amber-700 text-white rounded-lg text-xs font-bold"
                                    >
                                        Use this token →
                                    </button>
                                </div>
                            )}

                            <Link to="/login" className="inline-flex items-center gap-1 text-sm text-brand-600 hover:text-brand-700 font-medium">
                                <ArrowLeft size={14} /> Back to sign in
                            </Link>
                        </div>
                    ) : (
                        <form onSubmit={handleSubmit} className="space-y-6">
                            <div>
                                <label className="block text-sm font-medium text-slate-700">Email address</label>
                                <div className="mt-1 relative">
                                    <Mail size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                                    <input
                                        type="email"
                                        required
                                        value={email}
                                        onChange={(e) => setEmail(e.target.value)}
                                        className="appearance-none block w-full pl-9 pr-3 py-2 border border-slate-300 rounded-lg shadow-sm focus:outline-none focus:ring-brand-500 focus:border-brand-500 sm:text-sm"
                                        placeholder="you@example.com"
                                    />
                                </div>
                                <p className="mt-2 text-xs text-slate-500">
                                    We'll send a single-use link valid for 60 minutes. For security, the response is the same whether or not the email is registered.
                                </p>
                            </div>

                            <button
                                type="submit"
                                disabled={isSubmitting}
                                className="w-full flex justify-center py-2.5 px-4 border border-transparent rounded-lg shadow-sm text-sm font-medium text-white bg-brand-600 hover:bg-brand-700 disabled:opacity-50"
                            >
                                {isSubmitting ? 'Sending...' : 'Send reset link'}
                            </button>

                            <div className="text-center">
                                <Link to="/login" className="inline-flex items-center gap-1 text-sm text-slate-600 hover:text-slate-900">
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
