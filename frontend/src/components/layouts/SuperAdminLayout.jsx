import React, { useState } from 'react';
import { Outlet, NavLink, useNavigate } from 'react-router-dom';
import {
    LayoutDashboard, Building2, CreditCard, Settings,
    ShieldAlert, LogOut, Search, Activity
} from 'lucide-react';

export default function SuperAdminLayout() {
    const navigate = useNavigate();
    
    const NAV = [
        { name: 'Overview', path: '/superadmin/dashboard', icon: <LayoutDashboard size={20} /> },
        { name: 'Tenants & Hospitals', path: '/superadmin/tenants', icon: <Building2 size={20} /> },
        { name: 'Billing & Subscriptions', path: '/superadmin/billing', icon: <CreditCard size={20} /> },
        { name: 'Platform Settings', path: '/superadmin/settings', icon: <Settings size={20} /> }
    ];

    return (
        <div className="flex h-screen bg-slate-950 text-slate-300 font-sans overflow-hidden">
            {/* Sidebar */}
            <aside className="w-64 bg-slate-900 border-r border-slate-800 flex flex-col z-20">
                <div className="h-16 flex items-center gap-3 px-6 border-b border-slate-800 shrink-0">
                    <div className="w-8 h-8 bg-gradient-to-br from-amber-500 to-orange-600 rounded-lg flex items-center justify-center shadow-lg shadow-orange-500/20">
                        <ShieldAlert size={18} className="text-white" />
                    </div>
                    <span className="font-black text-white tracking-tight text-lg">HMS <span className="text-amber-500">Global</span></span>
                </div>

                <div className="p-4 border-b border-slate-800 bg-slate-900/50">
                    <div className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-1">Access Level</div>
                    <div className="flex items-center gap-2 text-amber-500 text-sm font-bold">
                        <div className="w-2 h-2 rounded-full bg-amber-500 animate-pulse"></div>
                        SUPER ADMIN
                    </div>
                </div>

                <nav className="flex-1 py-4 px-3 space-y-1">
                    {NAV.map((item) => (
                        <NavLink 
                            key={item.name} 
                            to={item.path} 
                            className={({isActive}) => `flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all font-medium text-sm ${isActive ? 'bg-slate-800 text-white shadow-sm border border-slate-700' : 'hover:bg-slate-800/50 hover:text-white'}`}
                        >
                            {({isActive}) => (
                                <>
                                    <span className={isActive ? 'text-amber-500' : 'text-slate-500'}>{item.icon}</span>
                                    {item.name}
                                </>
                            )}
                        </NavLink>
                    ))}
                </nav>

                <div className="p-4 border-t border-slate-800">
                    <button onClick={() => navigate('/login')} className="flex items-center gap-2 text-sm font-bold text-slate-500 hover:text-red-500 transition-colors w-full px-3 py-2 rounded-lg hover:bg-red-500/10">
                        <LogOut size={18} /> Exit Console
                    </button>
                </div>
            </aside>

            {/* Main Content Area */}
            <div className="flex-1 flex flex-col min-w-0 bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-slate-900 via-slate-950 to-slate-950">
                <header className="h-16 border-b border-slate-800/50 flex items-center justify-between px-8 shrink-0 bg-slate-900/30 backdrop-blur-md">
                    <div className="flex items-center gap-4 text-sm font-bold text-slate-400">
                        <Activity size={18} className="text-emerald-500" /> All Systems Operational
                    </div>
                    
                    <div className="flex items-center gap-6">
                        <div className="relative">
                            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
                            <input type="text" placeholder="Quick search tenants..." className="bg-slate-900 border border-slate-700 rounded-full pl-9 pr-4 py-1.5 text-sm text-white focus:outline-none focus:border-amber-500 w-64 transition-colors" />
                        </div>
                    </div>
                </header>

                <main className="flex-1 overflow-y-auto p-8 custom-scrollbar relative">
                    <Outlet />
                </main>
            </div>
        </div>
    );
}
