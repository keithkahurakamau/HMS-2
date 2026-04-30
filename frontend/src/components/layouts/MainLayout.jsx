import React, { useState } from 'react';
import { Outlet, NavLink, useLocation } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { 
    LayoutDashboard, Users, Stethoscope, TestTube, 
    Pill, Bed, Package, Receipt, LogOut, Menu, X, ShieldCheck,
    ClipboardList, Radio
} from 'lucide-react';

export default function MainLayout() {
    const { user, logout } = useAuth();
    const location = useLocation();
    const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

    const NAVIGATION = [
        { name: 'Command Center',    path: '/admin',           icon: <LayoutDashboard size={20} />, allowedRoles: ['Admin'] },
        { name: 'Patient Registry',  path: '/patients',        icon: <Users size={20} />,           allowedRoles: ['Admin', 'Receptionist', 'Doctor', 'Nurse'] },
        { name: 'Medical History',   path: '/medical-history', icon: <ClipboardList size={20} />,   allowedRoles: ['Admin', 'Doctor', 'Nurse'] },
        { name: 'Clinical Desk',     path: '/clinical',        icon: <Stethoscope size={20} />,     allowedRoles: ['Admin', 'Doctor'] },
        { name: 'Laboratory',        path: '/laboratory',      icon: <TestTube size={20} />,        allowedRoles: ['Admin', 'Lab Technician', 'Doctor'] },
        { name: 'Radiology',         path: '/radiology',       icon: <Radio size={20} />,           allowedRoles: ['Admin', 'Radiologist', 'Doctor'] },
        { name: 'Pharmacy',          path: '/pharmacy',        icon: <Pill size={20} />,            allowedRoles: ['Admin', 'Pharmacist', 'Doctor'] },
        { name: 'Wards & Admissions',path: '/wards',           icon: <Bed size={20} />,             allowedRoles: ['Admin', 'Nurse', 'Doctor'] },
        { name: 'Inventory Hub',     path: '/inventory',       icon: <Package size={20} />,         allowedRoles: ['Admin', 'Pharmacist', 'Lab Technician'] },
        { name: 'Billing & Finance', path: '/billing',         icon: <Receipt size={20} />,         allowedRoles: ['Admin', 'Receptionist'] },
    ];

    const filteredNav = NAVIGATION.filter(item => item.allowedRoles.includes(user?.role));
    const handleNavClick = () => setIsMobileMenuOpen(false);

    return (
        <div className="flex h-screen bg-slate-50 font-sans overflow-hidden">
            {isMobileMenuOpen && (
                <div className="fixed inset-0 bg-slate-900/50 z-40 md:hidden" onClick={() => setIsMobileMenuOpen(false)} />
            )}

            <aside className={`fixed inset-y-0 left-0 z-50 w-64 bg-slate-900 text-slate-300 flex flex-col transition-transform duration-300 ease-in-out md:relative md:translate-x-0 ${isMobileMenuOpen ? 'translate-x-0' : '-translate-x-full'}`}>
                <div className="h-16 flex items-center justify-between px-6 bg-slate-950/50 border-b border-slate-800 shrink-0">
                    <div className="flex items-center gap-2 font-black text-white text-xl tracking-tight">
                        <div className="w-8 h-8 bg-brand-600 rounded-lg flex items-center justify-center">
                            <ShieldCheck size={20} className="text-white" />
                        </div>
                        HMS <span className="text-brand-500 font-medium">Enterprise</span>
                    </div>
                    <button className="md:hidden text-slate-400 hover:text-white" onClick={() => setIsMobileMenuOpen(false)}><X size={24} /></button>
                </div>

                <nav className="flex-1 overflow-y-auto py-4 px-3 space-y-1 custom-scrollbar">
                    <div className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-2 px-3">Modules</div>
                    {filteredNav.map((item) => {
                        const isActive = location.pathname.startsWith(item.path);
                        return (
                            <NavLink key={item.name} to={item.path} onClick={handleNavClick} className={`flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all font-medium text-sm ${isActive ? 'bg-brand-600 text-white shadow-md' : 'hover:bg-slate-800 hover:text-white'}`}>
                                <span className={isActive ? 'text-white' : 'text-slate-400'}>{item.icon}</span>
                                {item.name}
                            </NavLink>
                        );
                    })}
                </nav>

                <div className="p-4 border-t border-slate-800 bg-slate-900 shrink-0">
                    <div className="flex items-center gap-3 bg-slate-800 p-3 rounded-xl border border-slate-700/50">
                        <div className="w-10 h-10 rounded-full bg-gradient-to-tr from-brand-500 to-accent-500 flex items-center justify-center text-white font-bold shadow-inner">
                            {user?.full_name?.charAt(0) || 'U'}
                        </div>
                        <div className="flex-1 min-w-0">
                            <p className="text-sm font-bold text-white truncate">{user?.full_name}</p>
                            <p className="text-xs text-brand-400 font-semibold truncate">{user?.role}</p>
                        </div>
                    </div>
                </div>
            </aside>

            <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
                <header className="h-16 bg-white border-b border-slate-200 flex items-center justify-between px-4 sm:px-6 shrink-0 z-10">
                    <div className="flex items-center gap-4">
                        <button className="md:hidden text-slate-500 hover:text-slate-800" onClick={() => setIsMobileMenuOpen(true)}><Menu size={24} /></button>
                        <h2 className="text-lg font-bold text-slate-800 hidden sm:block">
                            {filteredNav.find(n => location.pathname.startsWith(n.path))?.name || 'Dashboard'}
                        </h2>
                    </div>

                    <div className="flex items-center gap-4">
                        <div className="hidden sm:flex items-center gap-2 px-3 py-1.5 bg-green-50 border border-green-200 rounded-full">
                            <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
                            <span className="text-xs font-bold text-green-700 uppercase tracking-wider">System Online</span>
                        </div>
                        <button onClick={logout} className="flex items-center gap-2 text-sm font-bold text-slate-500 hover:text-red-600 transition-colors px-3 py-2 rounded-lg hover:bg-red-50">
                            <LogOut size={18} />
                            <span className="hidden sm:block">Sign Out</span>
                        </button>
                    </div>
                </header>

                <main className="flex-1 overflow-y-auto bg-slate-50/50 p-4 sm:p-6 custom-scrollbar">
                    <Outlet />
                </main>
            </div>
        </div>
    );
}