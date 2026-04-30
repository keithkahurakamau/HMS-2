import React from 'react';
import { NavLink } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { 
    LayoutDashboard, Users, CalendarDays, Stethoscope, 
    FlaskConical, Pill, Receipt, Box, BedDouble, ShieldAlert
} from 'lucide-react';

export default function Sidebar() {
    const { user } = useAuth();
    const userRole = user?.role || 'UNKNOWN';

    const navItems = [
        { name: 'Dashboard', path: '/dashboard', icon: LayoutDashboard, roles: ['ADMIN', 'DOCTOR', 'RECEPTIONIST', 'CASHIER', 'LAB_TECH', 'PHARMACIST'] },
        { name: 'Patients & Triage', path: '/patients', icon: Users, roles: ['ADMIN', 'RECEPTIONIST', 'DOCTOR'] },
        { name: 'Appointments', path: '/appointments', icon: CalendarDays, roles: ['ADMIN', 'RECEPTIONIST', 'DOCTOR'] },
        { name: 'Clinical Desk', path: '/clinical', icon: Stethoscope, roles: ['ADMIN', 'DOCTOR'] },
        { name: 'Laboratory', path: '/laboratory', icon: FlaskConical, roles: ['ADMIN', 'LAB_TECH', 'DOCTOR'] },
        { name: 'Pharmacy', path: '/pharmacy', icon: Pill, roles: ['ADMIN', 'PHARMACIST', 'DOCTOR'] },
        { name: 'Billing & POS', path: '/billing', icon: Receipt, roles: ['ADMIN', 'CASHIER'] },
        { name: 'Ward & Beds', path: '/wards', icon: BedDouble, roles: ['ADMIN', 'DOCTOR', 'RECEPTIONIST'] },
        { name: 'Inventory', path: '/inventory', icon: Box, roles: ['ADMIN', 'PHARMACIST', 'LAB_TECH'] },
        { name: 'System Admin', path: '/admin', icon: ShieldAlert, roles: ['ADMIN'] },
    ];

    const authorizedItems = navItems.filter(item => item.roles.includes(userRole));

    return (
        <div className="flex flex-col w-64 bg-slate-900 text-slate-300 h-full border-r border-slate-800">
            <div className="flex items-center justify-center h-16 border-b border-slate-800 px-4">
                <div className="flex items-center gap-2 text-white font-bold text-xl tracking-tight">
                    <div className="w-8 h-8 bg-brand-600 rounded-lg flex items-center justify-center">
                        <span className="text-white text-lg font-extrabold">+</span>
                    </div>
                    MayoClinic
                </div>
            </div>
            
            <div className="flex-1 overflow-y-auto py-4 px-3 space-y-1">
                <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-4 px-3">
                    Core Modules
                </div>
                {authorizedItems.map((item) => (
                    <NavLink
                        key={item.name}
                        to={item.path}
                        className={({ isActive }) =>
                            `flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200 ${
                                isActive 
                                ? 'bg-brand-600 text-white shadow-md' 
                                : 'hover:bg-slate-800 hover:text-white'
                            }`
                        }
                    >
                        <item.icon size={20} strokeWidth={1.5} />
                        <span className="font-medium text-sm">{item.name}</span>
                    </NavLink>
                ))}
            </div>
            
            <div className="p-4 border-t border-slate-800 bg-slate-850">
                <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-full bg-brand-100 flex items-center justify-center text-brand-700 font-bold border-2 border-brand-500">
                        {user?.full_name?.charAt(0) || 'U'}
                    </div>
                    <div className="flex flex-col overflow-hidden">
                        <span className="text-sm font-semibold text-white truncate">{user?.full_name}</span>
                        <span className="text-xs text-brand-400 font-medium">{userRole}</span>
                    </div>
                </div>
            </div>
        </div>
    );
}