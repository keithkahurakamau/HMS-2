import React from 'react';
import { Outlet } from 'react-router-dom';
import Sidebar from '../components/layout/Sidebar';
import Header from '../components/layout/Header';

export default function MainLayout() {
    return (
        <div className="flex h-screen bg-slate-50 overflow-hidden font-sans">
            <Sidebar />
            <div className="flex flex-col flex-1 overflow-hidden">
                <Header />
                <main className="flex-1 overflow-y-auto p-6 scroll-smooth">
                    {/* The specific page content (Dashboard, Patients, etc.) will render here */}
                    <div className="max-w-7xl mx-auto">
                        <Outlet /> 
                    </div>
                </main>
            </div>
        </div>
    );
}