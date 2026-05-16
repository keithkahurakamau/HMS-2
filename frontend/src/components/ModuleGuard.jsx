import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Lock, LifeBuoy, Sparkles } from 'lucide-react';
import { useModules } from '../context/ModuleContext';

/* ────────────────────────────────────────────────────────────────────────── */
/*  Route-level entitlement guard.                                            */
/*                                                                            */
/*  Usage in App.jsx:                                                         */
/*    <Route path="pharmacy" element={                                        */
/*      <ModuleGuard moduleKey="pharmacy"><Pharmacy /></ModuleGuard>          */
/*    } />                                                                    */
/*                                                                            */
/*  When the tenant doesn't own the module, this renders a full-page upgrade  */
/*  card that hands the user off to the in-app Support module with the        */
/*  ticket draft pre-filled. The server enforces the same rule at the        */
/*  middleware level (HTTP 402), so this is purely UX.                        */
/* ────────────────────────────────────────────────────────────────────────── */

const MODULE_LABELS = {
    pharmacy: 'Pharmacy',
    laboratory: 'Laboratory',
    radiology: 'Radiology',
    wards: 'Wards & In-Patient',
    inventory: 'Inventory',
    billing: 'Billing',
    cheques: 'Cheques',
    medical_history: 'Medical History',
    mpesa: 'M-Pesa',
    analytics: 'Analytics',
    patient_portal: 'Patient Portal',
    branding: 'Branding',
    referrals: 'Referrals',
    privacy: 'Privacy',
    clinical: 'Clinical Desk',
    accounting: 'Managerial Accounting',
};

export default function ModuleGuard({ moduleKey, children }) {
    const { hasModule, loading } = useModules();

    if (loading) {
        return (
            <div className="flex items-center justify-center min-h-[60vh]">
                <Sparkles className="animate-pulse text-brand-500" size={28} aria-label="Loading module" />
            </div>
        );
    }

    if (hasModule(moduleKey)) {
        return children;
    }

    return <UpgradeRequired moduleKey={moduleKey} />;
}

export function UpgradeRequired({ moduleKey, label }) {
    const navigate = useNavigate();
    const resolvedLabel = label || MODULE_LABELS[moduleKey] || moduleKey;

    const goToSupport = () => {
        navigate('/app/support', {
            state: {
                prefill: {
                    category: 'Account',
                    priority: 'Normal',
                    subject: `Upgrade request: ${resolvedLabel}`,
                    body:
                        `Hello MediFleet team,\n\n` +
                        `We would like to add the "${resolvedLabel}" module to our package. ` +
                        `Please advise on pricing and next steps.\n\n` +
                        `Thank you.`,
                },
            },
        });
    };

    return (
        <div className="min-h-[70vh] flex items-center justify-center p-6">
            <div className="max-w-xl w-full bg-white dark:bg-ink-900 border border-ink-200 dark:border-ink-700 rounded-2xl shadow-xl p-8 text-center">
                <div className="mx-auto w-14 h-14 rounded-full bg-amber-100 dark:bg-amber-900/30 flex items-center justify-center mb-4">
                    <Lock className="text-amber-600" size={26} aria-hidden />
                </div>
                <h2 className="text-2xl font-semibold mb-2">
                    {resolvedLabel} isn't part of your current package
                </h2>
                <p className="text-ink-600 dark:text-ink-300 mb-6">
                    This module is sold as an add-on. Contact the MediFleet support team
                    to upgrade and unlock <span className="font-medium">{resolvedLabel}</span> for
                    your hospital — we'll have it switched on in minutes.
                </p>
                <button
                    type="button"
                    onClick={goToSupport}
                    className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-brand-600 hover:bg-brand-700 text-white font-medium transition"
                >
                    <LifeBuoy size={18} aria-hidden />
                    Contact MediFleet Support to upgrade
                </button>
                <p className="text-xs text-ink-500 dark:text-ink-400 mt-4">
                    Your request opens a ticket with our team in the Support module — no email needed.
                </p>
            </div>
        </div>
    );
}
