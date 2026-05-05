import React from 'react';
import { Activity } from 'lucide-react';

export default function SuperAdminDashboard() {
    return (
        <div className="flex flex-col items-center justify-center h-full text-slate-500 animate-in fade-in duration-700">
            <Activity size={48} className="mb-4 text-amber-500/50" />
            <h2 className="text-xl font-bold text-white mb-2">Global Analytics Engine</h2>
            <p className="text-sm">Real-time metrics and revenue telemetry are being configured.</p>
        </div>
    );
}
