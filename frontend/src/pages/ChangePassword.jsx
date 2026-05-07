import React, { useState } from 'react';
import { apiClient } from '../api/client';
import toast from 'react-hot-toast';
import { ShieldCheck, Eye, EyeOff, Lock, Check } from 'lucide-react';

const RULES = [
    { label: 'At least 8 characters',          test: (v) => v.length >= 8 },
    { label: 'One uppercase letter',           test: (v) => /[A-Z]/.test(v) },
    { label: 'One lowercase letter',           test: (v) => /[a-z]/.test(v) },
    { label: 'One number',                     test: (v) => /\d/.test(v) },
    { label: 'One special character (!@#$…)',  test: (v) => /[!@#$%^&*(),.?":{}|<>]/.test(v) },
];

export default function ChangePassword({ userId, onSuccess }) {
    const [newPassword, setNewPassword] = useState('');
    const [confirm, setConfirm] = useState('');
    const [showNew, setShowNew] = useState(false);
    const [showConfirm, setShowConfirm] = useState(false);
    const [isSubmitting, setIsSubmitting] = useState(false);

    const allRulesMet    = RULES.every((r) => r.test(newPassword));
    const passwordsMatch = newPassword === confirm && confirm.length > 0;

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!allRulesMet) return toast.error('Password does not meet all requirements.');
        if (!passwordsMatch) return toast.error('Passwords do not match.');

        setIsSubmitting(true);
        try {
            await apiClient.post('/auth/change-password', { user_id: userId, new_password: newPassword });
            toast.success('Password changed! Please log in with your new credentials.');
            onSuccess();
        } catch (err) {
            const detail = err.response?.data?.detail;
            toast.error(Array.isArray(detail) ? (detail[0]?.msg || 'Invalid password.') : (detail || 'Failed to update password.'));
        } finally {
            setIsSubmitting(false);
        }
    };

    return (
        <div className="min-h-screen bg-ink-50 bg-mesh flex items-center justify-center p-4 sm:p-8">
            <div className="w-full max-w-md animate-slide-up">
                <div className="text-center mb-8">
                    <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-amber-500 ring-4 ring-amber-100 shadow-soft">
                        <ShieldCheck size={28} className="text-white" />
                    </div>
                    <h1 className="mt-5 text-2xl font-semibold text-ink-900 tracking-tight">Secure your account</h1>
                    <p className="mt-1.5 text-sm text-ink-500 leading-relaxed">
                        Your administrator has provisioned this account with a temporary password.
                        <br className="hidden sm:block" />Set a new password before continuing.
                    </p>
                </div>

                <div className="card p-7 sm:p-8">
                    <form onSubmit={handleSubmit} className="space-y-5">
                        <div>
                            <label htmlFor="new-pw" className="label">New password</label>
                            <div className="relative">
                                <Lock size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-ink-400" />
                                <input
                                    id="new-pw"
                                    type={showNew ? 'text' : 'password'}
                                    value={newPassword}
                                    onChange={(e) => setNewPassword(e.target.value)}
                                    placeholder="Enter new password"
                                    className="input pl-10 pr-10"
                                    required
                                />
                                <button
                                    type="button"
                                    onClick={() => setShowNew(!showNew)}
                                    aria-label={showNew ? 'Hide password' : 'Show password'}
                                    className="absolute right-2 top-1/2 -translate-y-1/2 p-2 rounded-lg text-ink-400 hover:text-ink-700 hover:bg-ink-100 transition-colors"
                                >
                                    {showNew ? <EyeOff size={16} /> : <Eye size={16} />}
                                </button>
                            </div>
                        </div>

                        <div>
                            <label htmlFor="confirm-pw" className="label">Confirm password</label>
                            <div className="relative">
                                <Lock size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-ink-400" />
                                <input
                                    id="confirm-pw"
                                    type={showConfirm ? 'text' : 'password'}
                                    value={confirm}
                                    onChange={(e) => setConfirm(e.target.value)}
                                    placeholder="Confirm new password"
                                    className={`input pl-10 pr-10 ${
                                        confirm.length > 0
                                            ? passwordsMatch
                                                ? 'border-accent-500 focus:border-accent-500 focus:ring-accent-500/20'
                                                : 'border-rose-400 focus:border-rose-500 focus:ring-rose-500/20'
                                            : ''
                                    }`}
                                    required
                                />
                                <button
                                    type="button"
                                    onClick={() => setShowConfirm(!showConfirm)}
                                    aria-label={showConfirm ? 'Hide password' : 'Show password'}
                                    className="absolute right-2 top-1/2 -translate-y-1/2 p-2 rounded-lg text-ink-400 hover:text-ink-700 hover:bg-ink-100 transition-colors"
                                >
                                    {showConfirm ? <EyeOff size={16} /> : <Eye size={16} />}
                                </button>
                            </div>
                        </div>

                        {newPassword.length > 0 && (
                            <div className="bg-ink-50 rounded-xl p-4 ring-1 ring-ink-100 space-y-2 animate-fade-in">
                                {RULES.map((rule) => {
                                    const ok = rule.test(newPassword);
                                    return (
                                        <div key={rule.label} className={`flex items-center gap-2 text-xs font-medium transition-colors ${ok ? 'text-accent-700' : 'text-ink-500'}`}>
                                            <span className={`w-4 h-4 rounded-full flex items-center justify-center shrink-0 ring-1 ring-inset ${ok ? 'bg-accent-100 ring-accent-200 text-accent-700' : 'bg-white ring-ink-200 text-ink-400'}`}>
                                                {ok ? <Check size={10} strokeWidth={3} /> : <span className="w-1 h-1 rounded-full bg-ink-300" />}
                                            </span>
                                            {rule.label}
                                        </div>
                                    );
                                })}
                            </div>
                        )}

                        <button
                            type="submit"
                            disabled={isSubmitting || !allRulesMet || !passwordsMatch}
                            className="btn-primary w-full py-3"
                        >
                            {isSubmitting ? 'Securing account…' : 'Set new password & continue'}
                        </button>
                    </form>
                </div>
            </div>
        </div>
    );
}
