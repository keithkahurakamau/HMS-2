import React, { useState, useEffect } from 'react';
import { Outlet, NavLink, useLocation } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { useModules } from '../../context/ModuleContext';
import { useJourney } from '../../context/JourneyContext';
import {
    LayoutDashboard, Users, Stethoscope, TestTube,
    Pill, Bed, Package, Receipt, LogOut, Menu, X,
    ClipboardList, Radio, CalendarDays, MessageSquare, Settings, Banknote, LifeBuoy,
    BookOpen, Smartphone, HelpCircle, HeartPulse, PanelLeftClose, PanelLeftOpen,
    CalendarClock, Home,
} from 'lucide-react';
import NotificationBell from '../NotificationBell';
import ThemeToggle from '../ThemeToggle';
import ActivePatientBar from '../ActivePatientBar';
import { TenantLogo } from '../Logo';
import { useBranding } from '../../context/BrandingContext';

// Route → module-key map for the on-first-visit tour. Module scope: static,
// no local deps, so it's built once rather than every render.
const ROUTE_TO_JOURNEY = [
    ['/app/admin',           'admin'],
    ['/app/patients',        'patients'],
    ['/app/triage',          'triage'],
    ['/app/clinical',        'clinical'],
    ['/app/laboratory',      'laboratory'],
    ['/app/radiology',       'radiology'],
    ['/app/pharmacy',        'pharmacy'],
    ['/app/inventory',       'inventory'],
    ['/app/wards',           'wards'],
    ['/app/billing',         'billing'],
    ['/app/cheques',         'cheques'],
    ['/app/medical-history', 'medical_history'],
    ['/app/appointments',    'appointments'],
    ['/app/calendar',        'appointments'],
    ['/app/messages',        'messages'],
    ['/app/settings',        'settings'],
    ['/app/branding',        'branding'],
    ['/app/accounting',      'accounting'],
    ['/app/support',         'support'],
    ['/app/mpesa-settings',  'payhero'],
    ['/app/home',            'dashboard'],
    ['/app/dashboard',       'dashboard'],
    ['/app',                 'dashboard'],   // role-redirect fallback
];

// Module nav config. Static (literals + module-scope icon imports), so it's
// allocated once. Each module declares legacy `allowedRoles` + a
// `requiredPermission`; we prefer permissions and fall back to role names.
const NAVIGATION = [
    // Home is the universal landing — visible to every role, no gate.
    { name: 'Home',              path: '/app/home',            icon: <Home size={18} />,            allowedRoles: ['Admin', 'Receptionist', 'Doctor', 'Nurse', 'Pharmacist', 'Lab Technician', 'Radiologist', 'Accountant'], moduleKey: null },
    { name: 'Command Center',    path: '/app/admin',           icon: <LayoutDashboard size={18} />, allowedRoles: ['Admin'],                                          requiredPermission: 'users:manage',     moduleKey: 'dashboard' },
    { name: 'Messages',          path: '/app/messages',        icon: <MessageSquare size={18} />,   allowedRoles: ['Admin', 'Doctor', 'Nurse', 'Pharmacist', 'Lab Technician', 'Radiologist', 'Receptionist'], requiredPermission: 'messaging:read', moduleKey: 'messaging' },
    { name: 'Patient Registry',  path: '/app/patients',        icon: <Users size={18} />,           allowedRoles: ['Admin', 'Receptionist', 'Doctor', 'Nurse'],       requiredPermission: 'patients:read',    moduleKey: 'patients' },
    { name: 'Medical History',   path: '/app/medical-history', icon: <ClipboardList size={18} />,   allowedRoles: ['Admin', 'Doctor', 'Nurse'],                       requiredPermission: 'history:read',     moduleKey: 'medical_history' },
    { name: 'Triage',            path: '/app/triage',          icon: <HeartPulse size={18} />,      allowedRoles: ['Admin', 'Nurse', 'Doctor'],                       requiredPermission: 'triage:read',      moduleKey: 'clinical' },
    { name: 'Clinical Desk',     path: '/app/clinical',        icon: <Stethoscope size={18} />,     allowedRoles: ['Admin', 'Doctor'],                                requiredPermission: 'clinical:read',    moduleKey: 'clinical' },
    { name: 'Laboratory',        path: '/app/laboratory',      icon: <TestTube size={18} />,        allowedRoles: ['Admin', 'Lab Technician', 'Doctor'],              requiredPermission: 'laboratory:read',  moduleKey: 'laboratory' },
    { name: 'Radiology',         path: '/app/radiology',       icon: <Radio size={18} />,           allowedRoles: ['Admin', 'Radiologist', 'Doctor'],                 requiredPermission: 'radiology:manage', moduleKey: 'radiology' },
    { name: 'Pharmacy',          path: '/app/pharmacy',        icon: <Pill size={18} />,            allowedRoles: ['Admin', 'Pharmacist', 'Doctor'],                  requiredPermission: 'pharmacy:read',    moduleKey: 'pharmacy' },
    { name: 'Wards & Admissions',path: '/app/wards',           icon: <Bed size={18} />,             allowedRoles: ['Admin', 'Nurse', 'Doctor'],                       requiredPermission: 'wards:manage',     moduleKey: 'wards' },
    { name: 'Appointments',      path: '/app/appointments',    icon: <CalendarDays size={18} />,    allowedRoles: ['Admin', 'Receptionist', 'Doctor', 'Nurse'],       requiredPermission: 'appointments:read',moduleKey: 'appointments' },
    // Calendar carries each user's personal events (every role gets one) plus
    // the appointments overlay for roles that can see appointments. No
    // permission gate — it's account-level — so it falls back to allowedRoles.
    { name: 'Calendar',          path: '/app/calendar',        icon: <CalendarClock size={18} />,   allowedRoles: ['Admin', 'Receptionist', 'Doctor', 'Nurse', 'Pharmacist', 'Lab Technician', 'Radiologist', 'Accountant'], moduleKey: 'appointments' },
    { name: 'Inventory Hub',     path: '/app/inventory',       icon: <Package size={18} />,         allowedRoles: ['Admin', 'Pharmacist', 'Lab Technician'],          requiredPermission: 'inventory:read',   moduleKey: 'inventory' },
    { name: 'Billing & Finance', path: '/app/billing',         icon: <Receipt size={18} />,         allowedRoles: ['Admin', 'Receptionist'],                          requiredPermission: 'billing:read',     moduleKey: 'billing' },
    { name: 'Cheque Register',   path: '/app/cheques',         icon: <Banknote size={18} />,        allowedRoles: ['Admin', 'Receptionist', 'Doctor', 'Nurse'],       requiredPermission: 'cheques:read',     moduleKey: 'cheques' },
    { name: 'Accounting',        path: '/app/accounting',      icon: <BookOpen size={18} />,        allowedRoles: ['Admin', 'Accountant'],                            requiredPermission: 'accounting:view',  moduleKey: 'accounting' },
    { name: 'MediFleet Support', path: '/app/support',         icon: <LifeBuoy size={18} />,        allowedRoles: ['Admin'],                                          requiredPermission: 'support:manage',   moduleKey: 'support' },
    { name: 'M-Pesa Payments',   path: '/app/mpesa-settings',  icon: <Smartphone size={18} />,      allowedRoles: ['Admin'],                                          requiredPermission: ['payhero:manage', 'mpesa:manage'], moduleKey: 'payhero' },
    { name: 'Settings',          path: '/app/settings',        icon: <Settings size={18} />,        allowedRoles: ['Admin'],                                          requiredPermission: 'settings:read',    moduleKey: 'settings' },
];

export default function MainLayout() {
    const { user, logout } = useAuth();
    const { hasModule, loading: modulesLoading } = useModules();
    const location = useLocation();
    const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
    // Desktop-only: collapse the sidebar for a full-width workspace view.
    // Persisted so the preference survives reloads; mobile keeps its own
    // overlay behaviour untouched.
    const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(
        () => localStorage.getItem('hms_sidebar_collapsed') === '1'
    );
    const toggleSidebar = () => setIsSidebarCollapsed((prev) => {
        const next = !prev;
        localStorage.setItem('hms_sidebar_collapsed', next ? '1' : '0');
        return next;
    });
    const { branding } = useBranding();
    const { startJourney, forceStartJourney, activeKey } = useJourney();

    const currentJourneyKey = ROUTE_TO_JOURNEY.find(
        ([prefix]) => location.pathname.startsWith(prefix)
    )?.[1] || null;

    useEffect(() => {
        if (!currentJourneyKey || activeKey) return;
        const id = setTimeout(() => startJourney(currentJourneyKey), 750);
        return () => clearTimeout(id);
    }, [currentJourneyKey, startJourney, activeKey]);

    // Get the dynamic hospital name from the portal selection
    const tenantName = localStorage.getItem('hms_tenant_name') || 'MediFleet';

    const userPerms = user?.permissions || [];
    const userRole = user?.role;
    const filteredNav = NAVIGATION.filter(item => {
        // 1) Module entitlement first — items the tenant didn't purchase are
        //    hidden entirely. While modules are still loading we show
        //    permission-allowed items so the sidebar isn't empty on first
        //    paint. Always-on modules are always present per ModuleContext.
        if (!modulesLoading && item.moduleKey && !hasModule(item.moduleKey)) {
            return false;
        }
        // 2) Permission-driven role gating wins. If we don't have permissions
        //    data yet (older client/server build), fall back to legacy role
        //    list.
        if (userPerms.length > 0 && item.requiredPermission) {
            const required = Array.isArray(item.requiredPermission)
                ? item.requiredPermission
                : [item.requiredPermission];
            return required.some(p => userPerms.includes(p));
        }
        return item.allowedRoles.includes(userRole);
    });
    const handleNavClick = () => setIsMobileMenuOpen(false);
    const currentSection = filteredNav.find(n => location.pathname.startsWith(n.path));

    return (
        <div className="flex h-screen bg-ink-50 dark:bg-ink-950 font-sans overflow-hidden">
            {isMobileMenuOpen && (
                <button
                    type="button"
                    aria-label="Close menu"
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
                            ${isSidebarCollapsed ? 'md:hidden' : 'md:relative md:translate-x-0'}
                            ${isMobileMenuOpen ? 'translate-x-0' : '-translate-x-full'}`}
            >
                {/* Brand block */}
                <div className="h-16 flex items-center justify-between px-5 border-b border-white/5 shrink-0">
                    <div className="flex items-center overflow-hidden">
                        <TenantLogo
                            src={branding.logo_data_url}
                            fallbackLabel={tenantName}
                            sublabel="Hospital"
                            size={36}
                            tone="mono-light"
                        />
                    </div>
                    <button type="button"
                        className="md:hidden text-ink-400 hover:text-white"
                        onClick={() => setIsMobileMenuOpen(false)}
                        aria-label="Close menu"
                    >
                        <X size={20} />
                    </button>
                </div>

                {/* Nav */}
                <nav data-tour="sidebar-nav" className="flex-1 overflow-y-auto py-5 px-3 custom-scrollbar">
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
                        <div className="size-10 rounded-full bg-gradient-to-br from-brand-400 to-accent-500 flex items-center justify-center text-white font-semibold shadow-glow shrink-0">
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
                        <button type="button"
                            className="md:hidden p-2 -ml-2 rounded-lg text-ink-500 hover:text-ink-900 hover:bg-ink-100 dark:text-ink-400 dark:hover:text-white dark:hover:bg-ink-800 transition-colors"
                            onClick={() => setIsMobileMenuOpen(true)}
                            aria-label="Open navigation menu"
                        >
                            <Menu size={20} aria-hidden="true" />
                        </button>
                        <button type="button"
                            className="hidden md:inline-flex p-2 -ml-2 rounded-lg text-ink-500 hover:text-ink-900 hover:bg-ink-100 dark:text-ink-400 dark:hover:text-white dark:hover:bg-ink-800 transition-colors"
                            onClick={toggleSidebar}
                            aria-label={isSidebarCollapsed ? 'Show sidebar' : 'Hide sidebar'}
                            title={isSidebarCollapsed ? 'Show sidebar' : 'Hide sidebar for a full-width workspace'}
                        >
                            {isSidebarCollapsed ? <PanelLeftOpen size={20} aria-hidden="true" /> : <PanelLeftClose size={20} aria-hidden="true" />}
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
                            <span className="relative flex size-2">
                                <span className="animate-pulse-soft absolute inline-flex h-full w-full rounded-full bg-accent-500 opacity-75"></span>
                                <span className="relative inline-flex rounded-full size-2 bg-accent-600"></span>
                            </span>
                            <span className="text-2xs font-semibold text-accent-700 dark:text-accent-400 uppercase tracking-wider">System Online</span>
                        </div>
                        {currentJourneyKey && (
                            <button
                                type="button"
                                data-tour="topbar-help"
                                onClick={() => forceStartJourney(currentJourneyKey)}
                                aria-label="Replay the tour for this page"
                                title="Replay tour for this page"
                                className="hidden sm:inline-flex p-2 rounded-lg text-ink-500 hover:text-brand-700 hover:bg-brand-50 dark:text-ink-400 dark:hover:text-brand-300 dark:hover:bg-brand-900/20 transition-colors"
                            >
                                <HelpCircle size={18} />
                            </button>
                        )}
                        <div data-tour="topbar-notifications"><NotificationBell /></div>
                        <ThemeToggle compact />
                        <div className="hidden sm:block w-px h-6 bg-ink-200 dark:bg-ink-800" />
                        <button type="button"
                            data-tour="topbar-signout"
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
                    {/* Active-patient bar — pinned at the top of the main outlet so
                        every workspace page renders the patient context above its
                        own header. Bar self-hides when no patient is active. */}
                    <div data-tour="active-patient-bar"><ActivePatientBar /></div>
                    <div className="animate-fade-in">
                        <Outlet />
                    </div>
                </main>
            </div>
        </div>
    );
}
