import React from 'react';
import { Activity, Building2, CreditCard, Users, TrendingUp } from 'lucide-react';

export default function SuperAdminDashboard() {
    return (
        <div className="space-y-6 animate-fade-in">
            <div>
                <span className="text-2xs font-semibold uppercase tracking-[0.16em] text-amber-400">Console</span>
                <h1 className="text-2xl font-semibold text-white tracking-tight mt-1">Global Overview</h1>
                <p className="text-sm text-ink-400 mt-1">Real-time platform metrics and revenue telemetry across all tenants.</p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                {[
                    { icon: Building2,  label: 'Active tenants',  value: '—', accent: 'amber'   },
                    { icon: Users,      label: 'Total users',     value: '—', accent: 'brand'   },
                    { icon: CreditCard, label: 'MRR',             value: '—', accent: 'accent'  },
                    { icon: TrendingUp, label: 'Growth (30d)',    value: '—', accent: 'blue'    },
                ].map(({ icon: Icon, label, value, accent }) => {
                    const ringMap = {
                        amber:  'bg-amber-500/10 ring-amber-500/20 text-amber-400',
                        brand:  'bg-brand-500/10 ring-brand-500/20 text-brand-300',
                        accent: 'bg-accent-500/10 ring-accent-500/20 text-accent-400',
                        blue:   'bg-blue-500/10 ring-blue-500/20 text-blue-400',
                    };
                    return (
                        <div key={label} className="bg-white/[0.04] backdrop-blur-md ring-1 ring-white/10 rounded-2xl p-5 hover:bg-white/[0.06] transition-colors">
                            <div className="flex justify-between items-start mb-4">
                                <div className={`w-10 h-10 rounded-xl flex items-center justify-center ring-1 ring-inset ${ringMap[accent]}`}>
                                    <Icon size={18} />
                                </div>
                            </div>
                            <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-ink-400">{label}</p>
                            <p className="text-2xl font-semibold text-white mt-1 tracking-tight">{value}</p>
                        </div>
                    );
                })}
            </div>

            <div className="bg-white/[0.04] backdrop-blur-md ring-1 ring-white/10 rounded-2xl p-12 text-center">
                <Activity size={40} className="mx-auto mb-3 text-amber-500/60" />
                <h2 className="text-lg font-semibold text-white">Global Analytics Engine</h2>
                <p className="text-sm text-ink-400 mt-1 max-w-md mx-auto">Real-time metrics and revenue telemetry are being configured. Charts will appear here once the analytics service is wired up.</p>
            </div>
        </div>
    );
}
