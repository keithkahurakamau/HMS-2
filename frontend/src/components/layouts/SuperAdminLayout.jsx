import React from 'react';
import { Outlet, NavLink, useNavigate } from 'react-router-dom';
import {
    LayoutDashboard, Building2, CreditCard, Settings,
    ShieldAlert, LogOut, Search, Activity, Users, LifeBuoy
} from 'lucide-react';
import { clearSuperAdminSession } from '../../pages/superadmin/SuperAdminLogin';
import Logo from '../Logo';

export default function SuperAdminLayout() {
    const navigate = useNavigate();
    const adminName = localStorage.getItem('hms_superadmin_name');

    const handleExit = () => {
        clearSuperAdminSession();
        navigate('/superadmin/login', { replace: true });
    };

    const NAV = [
        { name: 'Overview',                 path: '/superadmin/dashboard', icon: <LayoutDashboard size={18} /> },
        { name: 'Tenants & Hospitals',      path: '/superadmin/tenants',   icon: <Building2 size={18} /> },
        { name: 'Patients (read-only)',     path: '/superadmin/patients',  icon: <Users size={18} /> },
        { name: 'Support Inbox',            path: '/superadmin/support',   icon: <LifeBuoy size={18} /> },
        { name: 'Billing & Subscriptions',  path: '/superadmin/billing',   icon: <CreditCard size={18} /> },
        { name: 'Platform Settings',        path: '/superadmin/settings',  icon: <Settings size={18} /> },
    ];

    return (
        <div className="flex h-screen bg-ink-950 text-ink-300 font-sans overflow-hidden">
            {/* Sidebar */}
            <aside className="w-72 bg-gradient-to-b from-ink-900 via-ink-900 to-ink-950 border-r border-white/5 flex flex-col z-20">
                <div className="h-16 flex items-center gap-3 px-5 border-b border-white/5 shrink-0">
                    <Logo variant="full" size={32} label="MediFleet" sublabel="Platform" tone="mono-light" />
                    <span className="ml-auto inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-amber-500/15 ring-1 ring-amber-400/30">
                        <ShieldAlert size={11} className="text-amber-300" />
                        <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-amber-300">Console</span>
                    </span>
                </div>

                <div className="px-5 py-4 border-b border-white/5">
                    <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-ink-500 mb-1.5">Access level</div>
                    <div className="flex items-center gap-2 text-amber-400 text-xs font-semibold">
                        <span className="relative flex h-2 w-2">
                            <span className="animate-pulse-soft absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-70" />
                            <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-500" />
                        </span>
                        SUPER ADMIN
                    </div>
                </div>

                <nav className="flex-1 py-4 px-3 custom-scrollbar overflow-y-auto">
                    <div className="text-[10px] font-semibold tracking-[0.2em] uppercase text-ink-500 mb-3 px-3">Console</div>
                    <div className="space-y-0.5">
                        {NAV.map((item) => (
                            <NavLink key={item.name} to={item.path}
                                className={({isActive}) => `nav-link ${isActive ? 'nav-link-active' : ''}`}>
                                {({isActive}) => (
                                    <>
                                        <span className={isActive ? 'text-amber-400' : 'text-ink-400'}>{item.icon}</span>
                                        <span className="truncate">{item.name}</span>
                                    </>
                                )}
                            </NavLink>
                        ))}
                    </div>
                </nav>

                <div className="p-4 border-t border-white/5">
                    {adminName && (
                        <div className="mb-2 px-3 text-2xs text-ink-500 uppercase tracking-[0.16em] truncate">
                            Signed in as <span className="text-amber-300/90 normal-case tracking-normal">{adminName}</span>
                        </div>
                    )}
                    <button onClick={handleExit} className="flex items-center gap-2 text-sm font-semibold text-ink-400 hover:text-rose-400 transition-colors w-full px-3 py-2 rounded-lg hover:bg-rose-500/10">
                        <LogOut size={16} /> Exit console
                    </button>
                </div>
            </aside>

            {/* Main Content Area */}
            <div className="flex-1 flex flex-col min-w-0 relative">
                {/* Ambient glow */}
                <div className="absolute inset-0 pointer-events-none">
                    <div className="absolute -top-40 -right-32 w-96 h-96 bg-amber-500/10 rounded-full blur-[120px]" />
                    <div className="absolute -bottom-40 -left-20 w-96 h-96 bg-brand-500/10 rounded-full blur-[120px]" />
                </div>

                <header className="relative h-16 border-b border-white/5 flex items-center justify-between px-6 sm:px-8 shrink-0 bg-ink-900/30 backdrop-blur-md z-10">
                    <div className="flex items-center gap-2 pl-2.5 pr-3 py-1.5 bg-accent-500/10 ring-1 ring-accent-500/20 rounded-full">
                        <Activity size={14} className="text-accent-400" />
                        <span className="text-2xs font-semibold text-accent-300 uppercase tracking-wider">All systems operational</span>
                    </div>

                    <div className="flex items-center gap-4">
                        <div className="relative">
                            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-500" />
                            <input
                                type="text"
                                placeholder="Quick search tenants…"
                                className="bg-ink-900/60 border border-white/10 rounded-full pl-9 pr-4 py-1.5 text-sm text-white placeholder-ink-500 focus:outline-none focus:border-amber-500 focus:ring-2 focus:ring-amber-500/20 w-64 transition-all"
                            />
                        </div>
                    </div>
                </header>

                <main className="relative flex-1 overflow-y-auto p-6 sm:p-8 custom-scrollbar">
                    <div className="animate-fade-in">
                        <Outlet />
                    </div>
                </main>
            </div>
        </div>
    );
}
