import React, { useState } from 'react';
import { Outlet, NavLink, useLocation } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import {
    LayoutDashboard, Users, Stethoscope, TestTube,
    Pill, Bed, Package, Receipt, LogOut, Menu, X, ShieldCheck,
    ClipboardList, Radio, CalendarDays, MessageSquare, Settings
} from 'lucide-react';
import NotificationBell from '../NotificationBell';
import ThemeToggle from '../ThemeToggle';

export default function MainLayout() {
    const { user, logout } = useAuth();
    const location = useLocation();
    const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

    // Get the dynamic hospital name from the portal selection
    const tenantName = localStorage.getItem('hms_tenant_name') || 'HMS Enterprise';

    // Each module declares both legacy `allowedRoles` and a `requiredPermission`.
    // We prefer permissions so admin-created custom roles light up modules they
    // have access to, and fall back to role-name matching for users on builds
    // where a permission codename hasn't been seeded yet.
    const NAVIGATION = [
        { name: 'Command Center',    path: '/app/admin',           icon: <LayoutDashboard size={18} />, allowedRoles: ['Admin'],                                          requiredPermission: 'users:manage' },
        { name: 'Messages',          path: '/app/messages',        icon: <MessageSquare size={18} />,   allowedRoles: ['Admin', 'Doctor', 'Nurse', 'Pharmacist', 'Lab Technician', 'Radiologist', 'Receptionist'], requiredPermission: 'messaging:read' },
        { name: 'Patient Registry',  path: '/app/patients',        icon: <Users size={18} />,           allowedRoles: ['Admin', 'Receptionist', 'Doctor', 'Nurse'],       requiredPermission: 'patients:read' },
        { name: 'Medical History',   path: '/app/medical-history', icon: <ClipboardList size={18} />,   allowedRoles: ['Admin', 'Doctor', 'Nurse'],                       requiredPermission: 'history:read' },
        { name: 'Clinical Desk',     path: '/app/clinical',        icon: <Stethoscope size={18} />,     allowedRoles: ['Admin', 'Doctor'],                                requiredPermission: 'clinical:read' },
        { name: 'Laboratory',        path: '/app/laboratory',      icon: <TestTube size={18} />,        allowedRoles: ['Admin', 'Lab Technician', 'Doctor'],              requiredPermission: 'laboratory:read' },
        { name: 'Radiology',         path: '/app/radiology',       icon: <Radio size={18} />,           allowedRoles: ['Admin', 'Radiologist', 'Doctor'],                 requiredPermission: 'radiology:manage' },
        { name: 'Pharmacy',          path: '/app/pharmacy',        icon: <Pill size={18} />,            allowedRoles: ['Admin', 'Pharmacist', 'Doctor'],                  requiredPermission: 'pharmacy:read' },
        { name: 'Wards & Admissions',path: '/app/wards',           icon: <Bed size={18} />,             allowedRoles: ['Admin', 'Nurse', 'Doctor'],                       requiredPermission: 'wards:manage' },
        { name: 'Appointments',      path: '/app/appointments',    icon: <CalendarDays size={18} />,    allowedRoles: ['Admin', 'Receptionist', 'Doctor', 'Nurse'],       requiredPermission: 'patients:read' },
        { name: 'Inventory Hub',     path: '/app/inventory',       icon: <Package size={18} />,         allowedRoles: ['Admin', 'Pharmacist', 'Lab Technician'],          requiredPermission: 'pharmacy:read' },
        { name: 'Billing & Finance', path: '/app/billing',         icon: <Receipt size={18} />,         allowedRoles: ['Admin', 'Receptionist'],                          requiredPermission: 'billing:read' },
        { name: 'Settings',          path: '/app/settings',        icon: <Settings size={18} />,        allowedRoles: ['Admin'],                                          requiredPermission: 'settings:read' },
    ];

    const userPerms = user?.permissions || [];
    const userRole = user?.role;
    const filteredNav = NAVIGATION.filter(item => {
        // Permission-driven gating wins. If we don't have permissions data
        // yet (older client/server build), fall back to the legacy role list.
        if (userPerms.length > 0 && item.requiredPermission) {
            return userPerms.includes(item.requiredPermission);
        }
        return item.allowedRoles.includes(userRole);
    });
    const handleNavClick = () => setIsMobileMenuOpen(false);
    const currentSection = filteredNav.find(n => location.pathname.startsWith(n.path));

    return (
        <div className="flex h-screen bg-ink-50 dark:bg-ink-950 font-sans overflow-hidden">
            {isMobileMenuOpen && (
                <div
                    className="fixed inset-0 bg-ink-900/60 backdrop-blur-sm z-40 md:hidden animate-fade-in"
                    onClick={() => setIsMobileMenuOpen(false)}
                />
            )}

            <aside
                aria-label="Primary navigation"
                className={`fixed inset-y-0 left-0 z-50 w-72 flex flex-col
                            bg-gradient-to-b from-ink-900 via-ink-900 to-ink-950 text-ink-300
                            border-r border-white/5
                            transition-transform duration-300 ease-out
                            md:relative md:translate-x-0
                            ${isMobileMenuOpen ? 'translate-x-0' : '-translate-x-full'}`}
            >
                {/* Brand block */}
                <div className="h-16 flex items-center justify-between px-5 border-b border-white/5 shrink-0">
                    <div className="flex items-center gap-3 overflow-hidden">
                        <div className="w-9 h-9 rounded-xl bg-brand-gradient flex items-center justify-center shadow-glow shrink-0">
                            <ShieldCheck size={18} className="text-white" />
                        </div>
                        <div className="min-w-0">
                            <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-brand-300/80 leading-none">Hospital</div>
                            <div className="text-sm font-semibold text-white truncate leading-tight mt-0.5" title={tenantName}>{tenantName}</div>
                        </div>
                    </div>
                    <button
                        className="md:hidden text-ink-400 hover:text-white"
                        onClick={() => setIsMobileMenuOpen(false)}
                        aria-label="Close menu"
                    >
                        <X size={20} />
                    </button>
                </div>

                {/* Nav */}
                <nav className="flex-1 overflow-y-auto py-5 px-3 custom-scrollbar">
                    <div className="text-[10px] font-semibold tracking-[0.2em] uppercase text-ink-500 mb-3 px-3">
                        Modules
                    </div>
                    <div className="space-y-0.5">
                        {filteredNav.map((item) => {
                            const isActive = location.pathname.startsWith(item.path);
                            return (
                                <NavLink
                                    key={item.name}
                                    to={item.path}
                                    onClick={handleNavClick}
                                    className={`nav-link ${isActive ? 'nav-link-active' : ''}`}
                                >
                                    <span className={`shrink-0 ${isActive ? 'text-brand-300' : 'text-ink-400 group-hover:text-white'}`}>
                                        {item.icon}
                                    </span>
                                    <span className="truncate">{item.name}</span>
                                </NavLink>
                            );
                        })}
                    </div>
                </nav>

                {/* User card */}
                <div className="p-4 border-t border-white/5 shrink-0">
                    <div className="flex items-center gap-3 p-2.5 rounded-xl bg-white/[0.04] ring-1 ring-white/5">
                        <div className="w-10 h-10 rounded-full bg-gradient-to-br from-brand-400 to-accent-500 flex items-center justify-center text-white font-semibold shadow-glow shrink-0">
                            {user?.full_name?.charAt(0) || 'U'}
                        </div>
                        <div className="flex-1 min-w-0">
                            <p className="text-sm font-semibold text-white truncate leading-tight">{user?.full_name}</p>
                            <p className="text-xs text-brand-300/90 font-medium truncate mt-0.5">{user?.role}</p>
                        </div>
                    </div>
                </div>
            </aside>

            {/* Main column */}
            <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
                <header className="relative h-16 bg-white/80 dark:bg-ink-900/70 backdrop-blur-md border-b border-ink-200/70 dark:border-ink-800 flex items-center justify-between px-4 sm:px-6 shrink-0 z-40">
                    <div className="flex items-center gap-3 min-w-0">
                        <button
                            className="md:hidden p-2 -ml-2 rounded-lg text-ink-500 hover:text-ink-900 hover:bg-ink-100 dark:text-ink-400 dark:hover:text-white dark:hover:bg-ink-800 transition-colors"
                            onClick={() => setIsMobileMenuOpen(true)}
                            aria-label="Open navigation menu"
                        >
                            <Menu size={20} aria-hidden="true" />
                        </button>
                        <div className="hidden sm:block min-w-0">
                            <div className="text-2xs font-semibold uppercase tracking-[0.14em] text-ink-400 leading-none">Workspace</div>
                            <h2 className="text-base font-semibold text-ink-900 dark:text-white truncate mt-0.5">
                                {currentSection?.name || 'Dashboard'}
                            </h2>
                        </div>
                    </div>

                    <div className="flex items-center gap-2 sm:gap-3">
                        <div className="hidden sm:flex items-center gap-2 pl-2.5 pr-3 py-1.5 bg-accent-50 dark:bg-accent-700/15 ring-1 ring-inset ring-accent-100 dark:ring-accent-700/30 rounded-full">
                            <span className="relative flex h-2 w-2">
                                <span className="animate-pulse-soft absolute inline-flex h-full w-full rounded-full bg-accent-500 opacity-75"></span>
                                <span className="relative inline-flex rounded-full h-2 w-2 bg-accent-600"></span>
                            </span>
                            <span className="text-2xs font-semibold text-accent-700 dark:text-accent-400 uppercase tracking-wider">System Online</span>
                        </div>
                        <NotificationBell />
                        <ThemeToggle compact />
                        <div className="hidden sm:block w-px h-6 bg-ink-200 dark:bg-ink-800" />
                        <button
                            onClick={logout}
                            aria-label="Sign out"
                            className="flex items-center gap-2 text-sm font-semibold text-ink-500 hover:text-red-600 dark:text-ink-400 dark:hover:text-red-400 transition-colors px-3 py-2 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20"
                        >
                            <LogOut size={16} aria-hidden="true" />
                            <span className="hidden sm:block">Sign Out</span>
                        </button>
                    </div>
                </header>

                <main
                    id="main-content"
                    tabIndex={-1}
                    className="flex-1 overflow-y-auto bg-ink-50 dark:bg-ink-950 p-4 sm:p-6 lg:p-8 custom-scrollbar"
                >
                    <div className="animate-fade-in">
                        <Outlet />
                    </div>
                </main>
            </div>
        </div>
    );
}
