import React from 'react';
import { useAuth } from '../../context/AuthContext';
import { Bell, Search, LogOut } from 'lucide-react';

export default function Header() {
    const { logout } = useAuth();

    return (
        <header className="h-16 bg-white border-b border-slate-200 flex items-center justify-between px-6 z-10 shadow-sm shrink-0">
            <div className="flex items-center bg-slate-100 px-3 py-1.5 rounded-lg w-96 border border-slate-200 focus-within:border-blue-500 focus-within:ring-1 focus-within:ring-blue-500 transition-all">
                <Search size={18} className="text-slate-400" />
                <input 
                    type="text" 
                    placeholder="Search patients by OP Number or Name..." 
                    className="bg-transparent border-none focus:outline-none ml-2 text-sm w-full text-slate-700 placeholder-slate-400"
                />
            </div>

            <div className="flex items-center gap-4">
                <button 
                    onClick={logout}
                    className="flex items-center gap-2 text-sm font-medium text-slate-600 hover:text-red-600 px-3 py-1.5 rounded-lg hover:bg-red-50 transition-colors"
                >
                    <LogOut size={18} />
                    Logout
                </button>
            </div>
        </header>
    );
}