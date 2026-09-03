import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Lock, LifeBuoy } from 'lucide-react';
import { useModules } from '../context/ModuleContext';
import { Skeleton } from './ui/Skeleton';

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
    mpesa: 'M-Pesa Payments',
    analytics: 'Analytics',
    patient_portal: 'Patient Portal',
    branding: 'Branding',
    referrals: 'Referrals',
    privacy: 'Privacy',
    clinical: 'Clinical Desk',
    accounting: 'Managerial Accounting',
    maternity: 'Maternity',
};

export default function ModuleGuard({ moduleKey, children }) {
    const { hasModule, loading } = useModules();

    if (loading) {
        // A placeholder shaped like the card that is about to appear, rather
        // than a decorative spinner. The layout stays still when it resolves.
        return (
            <div className="min-h-[70vh] flex items-center justify-center p-6">
                <div className="max-w-xl w-full card p-8" role="status" aria-live="polite">
                    <span className="sr-only">Loading module</span>
                    <Skeleton className="mx-auto size-14 rounded-full" />
                    <Skeleton className="mx-auto mt-4 h-6 w-3/4" />
                    <Skeleton className="mx-auto mt-3 h-4 w-full" />
                    <Skeleton className="mx-auto mt-2 h-4 w-5/6" />
                </div>
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
            <div className="max-w-xl w-full card p-8 text-center">
                <div className="mx-auto size-14 rounded-full bg-amber-100 dark:bg-amber-900/30 flex items-center justify-center mb-4">
                    <Lock className="text-status-warn" size={26} aria-hidden />
                </div>
                <h2 className="t-heading mb-2">
                    {resolvedLabel} isn't part of your current package
                </h2>
                <p className="t-body mb-6">
                    This module is sold as an add-on. Contact the MediFleet support team
                    to upgrade and unlock <span className="font-medium">{resolvedLabel}</span> for
                    your hospital, and we'll have it switched on in minutes.
                </p>
                <button type="button" onClick={goToSupport} className="btn btn-primary">
                    <LifeBuoy size={18} aria-hidden />
                    Contact MediFleet Support to upgrade
                </button>
                <p className="t-caption mt-4">
                    Your request opens a ticket with our team in the Support module, so no email is needed.
                </p>
            </div>
        </div>
    );
}
