import React, { useState, useEffect } from 'react';
import { apiClient } from '../api/client';
import toast from 'react-hot-toast';
import { UserCog, Save, Activity, ShieldCheck, Stethoscope, BadgeCheck } from 'lucide-react';
import PageHeader from '../components/PageHeader';
import { useAuth } from '../context/AuthContext';

// Roles for whom the clinical-identity fields (specialization, licence) make
// sense — others don't see them.
const CLINICAL_ROLES = ['Doctor', 'Nurse', 'Pharmacist', 'Lab Technician', 'Radiologist'];

export default function Profile() {
    const { user, refreshUser } = useAuth();
    const isClinical = CLINICAL_ROLES.includes(user?.role);

    const [profile, setProfile] = useState(null);
    const [form, setForm] = useState({ full_name: '', specialization: '', license_number: '' });
    const [savingProfile, setSavingProfile] = useState(false);

    const [pwd, setPwd] = useState({ current_password: '', new_password: '', confirm: '' });
    const [savingPwd, setSavingPwd] = useState(false);

    useEffect(() => {
        apiClient.get('/users/me')
            .then((r) => {
                setProfile(r.data);
                setForm({
                    full_name: r.data.full_name || '',
                    specialization: r.data.specialization || '',
                    license_number: r.data.license_number || '',
                });
            })
            .catch(() => toast.error('Could not load your profile.'));
    }, []);

    const saveProfile = async () => {
        if (!form.full_name.trim()) { toast.error('Your name cannot be empty.'); return; }
        setSavingProfile(true);
        try {
            const payload = { full_name: form.full_name.trim() };
            if (isClinical) {
                payload.specialization = form.specialization.trim() || null;
                payload.license_number = form.license_number.trim() || null;
            }
            const r = await apiClient.patch('/users/me', payload);
            setProfile(r.data);
            toast.success('Profile updated.');
            refreshUser?.();
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Could not update profile.');
        } finally {
            setSavingProfile(false);
        }
    };

    const changePassword = async () => {
        if (!pwd.current_password || !pwd.new_password) { toast.error('Fill in both password fields.'); return; }
        if (pwd.new_password.length < 8) { toast.error('New password must be at least 8 characters.'); return; }
        if (pwd.new_password !== pwd.confirm) { toast.error('New password and confirmation do not match.'); return; }
        setSavingPwd(true);
        try {
            await apiClient.post('/users/me/change-password', {
                current_password: pwd.current_password,
                new_password: pwd.new_password,
            });
            toast.success('Password changed.');
            setPwd({ current_password: '', new_password: '', confirm: '' });
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Could not change password.');
        } finally {
            setSavingPwd(false);
        }
    };

    const initials = (profile?.full_name || user?.full_name || '?')
        .split(' ').map((s) => s[0]).slice(0, 2).join('').toUpperCase();

    return (
        <div className="space-y-6 pb-8 max-w-3xl">
            <PageHeader
                eyebrow="My account"
                icon={UserCog}
                title="Profile & security"
                subtitle="Keep your details current and manage your password."
            />

            {/* Identity card */}
            <div className="card p-5 flex items-center gap-4">
                <div className="size-16 rounded-full bg-gradient-to-br from-brand-400 to-accent-500 flex items-center justify-center text-white text-xl font-semibold shadow-glow shrink-0">
                    {initials}
                </div>
                <div className="min-w-0">
                    <p className="text-lg font-semibold text-ink-900 dark:text-white truncate">{profile?.full_name || user?.full_name}</p>
                    <p className="text-sm text-ink-500 dark:text-ink-400">{profile?.email || user?.email}</p>
                    <span className="inline-flex items-center gap-1 mt-1 text-2xs font-semibold px-2 py-0.5 rounded-md bg-brand-50 dark:bg-brand-500/10 text-brand-700 dark:text-brand-300">
                        <BadgeCheck size={12} /> {profile?.role || user?.role}
                    </span>
                </div>
            </div>

            {/* Profile details */}
            <div className="card p-5 space-y-4">
                <h2 className="section-eyebrow flex items-center gap-2"><UserCog size={15} /> Personal details</h2>
                <div>
                    <label htmlFor="prof-name" className="label">Full name</label>
                    <input id="prof-name" type="text" className="input" value={form.full_name}
                        onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
                </div>
                <div>
                    <label htmlFor="prof-email" className="label">Email</label>
                    <input id="prof-email" type="email" className="input opacity-60 cursor-not-allowed"
                        value={profile?.email || ''} disabled
                        title="Contact an administrator to change your sign-in email." />
                    <p className="text-2xs text-ink-500 dark:text-ink-400 mt-1">Your sign-in email is managed by an administrator.</p>
                </div>
                {isClinical && (
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                        <div>
                            <label htmlFor="prof-spec" className="label flex items-center gap-1"><Stethoscope size={13} /> Specialization</label>
                            <input id="prof-spec" type="text" className="input" value={form.specialization}
                                onChange={(e) => setForm({ ...form, specialization: e.target.value })}
                                placeholder="e.g. Paediatrics" />
                        </div>
                        <div>
                            <label htmlFor="prof-license" className="label">Licence number</label>
                            <input id="prof-license" type="text" className="input" value={form.license_number}
                                onChange={(e) => setForm({ ...form, license_number: e.target.value })}
                                placeholder="Professional registration no." />
                        </div>
                    </div>
                )}
                <div className="flex justify-end">
                    <button type="button" onClick={saveProfile} disabled={savingProfile} className="btn-primary">
                        {savingProfile ? <><Activity size={15} className="animate-spin" /> Saving…</> : <><Save size={15} /> Save changes</>}
                    </button>
                </div>
            </div>

            {/* Password */}
            <div className="card p-5 space-y-4">
                <h2 className="section-eyebrow flex items-center gap-2"><ShieldCheck size={15} /> Change password</h2>
                <div>
                    <label htmlFor="pwd-current" className="label">Current password</label>
                    <input id="pwd-current" type="password" autoComplete="current-password" className="input"
                        value={pwd.current_password} onChange={(e) => setPwd({ ...pwd, current_password: e.target.value })} />
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                        <label htmlFor="pwd-new" className="label">New password</label>
                        <input id="pwd-new" type="password" autoComplete="new-password" className="input"
                            value={pwd.new_password} onChange={(e) => setPwd({ ...pwd, new_password: e.target.value })} />
                        <p className="text-2xs text-ink-500 dark:text-ink-400 mt-1">At least 8 characters.</p>
                    </div>
                    <div>
                        <label htmlFor="pwd-confirm" className="label">Confirm new password</label>
                        <input id="pwd-confirm" type="password" autoComplete="new-password" className="input"
                            value={pwd.confirm} onChange={(e) => setPwd({ ...pwd, confirm: e.target.value })} />
                    </div>
                </div>
                <div className="flex justify-end">
                    <button type="button" onClick={changePassword} disabled={savingPwd} className="btn-primary">
                        {savingPwd ? <><Activity size={15} className="animate-spin" /> Updating…</> : <><ShieldCheck size={15} /> Update password</>}
                    </button>
                </div>
            </div>
        </div>
    );
}
