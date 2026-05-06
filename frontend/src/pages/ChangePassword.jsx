import React, { useState } from 'react';
import { apiClient } from '../api/client';
import toast from 'react-hot-toast';
import { ShieldCheck, Eye, EyeOff, Lock } from 'lucide-react';

const RULES = [
    { label: 'At least 8 characters', test: (v) => v.length >= 8 },
    { label: 'One uppercase letter', test: (v) => /[A-Z]/.test(v) },
    { label: 'One lowercase letter', test: (v) => /[a-z]/.test(v) },
    { label: 'One number', test: (v) => /\d/.test(v) },
    { label: 'One special character (!@#$…)', test: (v) => /[!@#$%^&*(),.?":{}|<>]/.test(v) },
];

export default function ChangePassword({ userId, onSuccess }) {
    const [newPassword, setNewPassword] = useState('');
    const [confirm, setConfirm] = useState('');
    const [showNew, setShowNew] = useState(false);
    const [showConfirm, setShowConfirm] = useState(false);
    const [isSubmitting, setIsSubmitting] = useState(false);

    const allRulesMet = RULES.every((r) => r.test(newPassword));
    const passwordsMatch = newPassword === confirm && confirm.length > 0;

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!allRulesMet) return toast.error('Password does not meet all requirements.');
        if (!passwordsMatch) return toast.error('Passwords do not match.');

        setIsSubmitting(true);
        try {
            await apiClient.post('/auth/change-password', {
                user_id: userId,
                new_password: newPassword,
            });
            toast.success('Password changed! Please log in with your new credentials.');
            onSuccess();
        } catch (err) {
            const detail = err.response?.data?.detail;
            if (Array.isArray(detail)) {
                toast.error(detail[0]?.msg || 'Invalid password.');
            } else {
                toast.error(detail || 'Failed to update password.');
            }
        } finally {
            setIsSubmitting(false);
        }
    };

    return (
        <div className="min-h-screen bg-gradient-to-br from-slate-900 via-blue-950 to-slate-900 flex items-center justify-center p-4">
            <div className="w-full max-w-md">
                {/* Header Card */}
                <div className="bg-white/10 backdrop-blur-md border border-white/20 rounded-2xl p-8 shadow-2xl">
                    <div className="flex flex-col items-center mb-8">
                        <div className="w-16 h-16 rounded-2xl bg-amber-500/20 border border-amber-500/40 flex items-center justify-center mb-4">
                            <ShieldCheck size={32} className="text-amber-400" />
                        </div>
                        <h1 className="text-2xl font-black text-white">Secure Your Account</h1>
                        <p className="text-slate-400 text-sm text-center mt-2">
                            Your administrator has provisioned this account with a temporary password.
                            <br />You must set a new password before continuing.
                        </p>
                    </div>

                    <form onSubmit={handleSubmit} className="space-y-5">
                        {/* New Password */}
                        <div>
                            <label className="block text-xs font-bold text-slate-300 mb-1.5 uppercase tracking-wider">
                                New Password
                            </label>
                            <div className="relative">
                                <Lock size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
                                <input
                                    type={showNew ? 'text' : 'password'}
                                    value={newPassword}
                                    onChange={(e) => setNewPassword(e.target.value)}
                                    placeholder="Enter new password"
                                    className="w-full pl-10 pr-10 py-3 bg-white/5 border border-white/20 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                                    required
                                />
                                <button type="button" onClick={() => setShowNew(!showNew)} className="absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white">
                                    {showNew ? <EyeOff size={16} /> : <Eye size={16} />}
                                </button>
                            </div>
                        </div>

                        {/* Confirm Password */}
                        <div>
                            <label className="block text-xs font-bold text-slate-300 mb-1.5 uppercase tracking-wider">
                                Confirm Password
                            </label>
                            <div className="relative">
                                <Lock size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
                                <input
                                    type={showConfirm ? 'text' : 'password'}
                                    value={confirm}
                                    onChange={(e) => setConfirm(e.target.value)}
                                    placeholder="Confirm new password"
                                    className={`w-full pl-10 pr-10 py-3 bg-white/5 border rounded-xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 text-sm transition-colors ${
                                        confirm.length > 0 ? (passwordsMatch ? 'border-green-500/50 focus:ring-green-500' : 'border-red-500/50 focus:ring-red-500') : 'border-white/20 focus:ring-blue-500'
                                    }`}
                                    required
                                />
                                <button type="button" onClick={() => setShowConfirm(!showConfirm)} className="absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white">
                                    {showConfirm ? <EyeOff size={16} /> : <Eye size={16} />}
                                </button>
                            </div>
                        </div>

                        {/* Password Rules Checklist */}
                        {newPassword.length > 0 && (
                            <div className="bg-white/5 rounded-xl p-4 space-y-2">
                                {RULES.map((rule) => (
                                    <div key={rule.label} className={`flex items-center gap-2 text-xs font-medium transition-colors ${rule.test(newPassword) ? 'text-green-400' : 'text-slate-500'}`}>
                                        <span className={`w-4 h-4 rounded-full flex items-center justify-center text-[10px] font-black shrink-0 ${rule.test(newPassword) ? 'bg-green-500/20 text-green-400' : 'bg-white/10 text-slate-600'}`}>
                                            {rule.test(newPassword) ? '✓' : '·'}
                                        </span>
                                        {rule.label}
                                    </div>
                                ))}
                            </div>
                        )}

                        <button
                            type="submit"
                            disabled={isSubmitting || !allRulesMet || !passwordsMatch}
                            className="w-full py-3.5 rounded-xl font-black text-white bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-500 hover:to-blue-600 disabled:opacity-40 disabled:cursor-not-allowed transition-all shadow-lg shadow-blue-900/30 text-sm tracking-wide"
                        >
                            {isSubmitting ? 'Securing Account...' : 'Set New Password & Continue'}
                        </button>
                    </form>
                </div>
            </div>
        </div>
    );
}
