import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { Link, useNavigate } from 'react-router-dom';
import { ShieldAlert, Activity } from 'lucide-react';
import ChangePassword from './ChangePassword';

export default function Login() {
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [isSubmitting, setIsSubmitting] = useState(false);
    
    const { login, mustChangePassword, pendingUserId, clearMustChange } = useAuth();
    const navigate = useNavigate();
    
    // Get dynamic tenant name
    const tenantName = localStorage.getItem('hms_tenant_name') || 'HMS Enterprise';

    const handleSubmit = async (e) => {
        e.preventDefault();
        setIsSubmitting(true);
        
        const result = await login(email, password);
        if (result?.success) {
            navigate('/app/dashboard');
        }
        // If mustChangePassword, the AuthContext state triggers the ChangePassword UI below
        
        setIsSubmitting(false);
    };

    // Show the forced password change screen if required
    if (mustChangePassword && pendingUserId) {
        return <ChangePassword userId={pendingUserId} onSuccess={() => { clearMustChange(); }} />;
    }

    return (
        <div className="min-h-screen bg-slate-50 flex flex-col justify-center py-12 sm:px-6 lg:px-8">
            <div className="sm:mx-auto sm:w-full sm:max-w-md">
                <div className="flex justify-center text-brand-600">
                    <Activity size={48} strokeWidth={1.5} />
                </div>
                <h2 className="mt-6 text-center text-3xl font-extrabold text-slate-900">
                    {tenantName}
                </h2>
                <p className="mt-2 text-center text-sm text-slate-600">
                    Enterprise Hospital Management System
                </p>
            </div>

            <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
                <div className="bg-white py-8 px-4 shadow-soft sm:rounded-xl sm:px-10 border border-slate-100">
                    <form className="space-y-6" onSubmit={handleSubmit}>
                        <div>
                            <label className="block text-sm font-medium text-slate-700">Email address</label>
                            <div className="mt-1">
                                <input
                                    type="email"
                                    required
                                    value={email}
                                    onChange={(e) => setEmail(e.target.value)}
                                    className="appearance-none block w-full px-3 py-2 border border-slate-300 rounded-lg shadow-sm placeholder-slate-400 focus:outline-none focus:ring-brand-500 focus:border-brand-500 sm:text-sm"
                                    placeholder="admin@mayoclinic.com"
                                />
                            </div>
                        </div>

                        <div>
                            <label className="block text-sm font-medium text-slate-700">Password</label>
                            <div className="mt-1">
                                <input
                                    type="password"
                                    required
                                    value={password}
                                    onChange={(e) => setPassword(e.target.value)}
                                    className="appearance-none block w-full px-3 py-2 border border-slate-300 rounded-lg shadow-sm placeholder-slate-400 focus:outline-none focus:ring-brand-500 focus:border-brand-500 sm:text-sm"
                                />
                            </div>
                        </div>

                        <div className="flex items-center justify-between text-sm">
                            <div className="flex items-center text-slate-500">
                                <ShieldAlert size={16} className="mr-2 text-brand-500" />
                                Secured via HttpOnly JWT
                            </div>
                            <Link to="/forgot-password" className="text-brand-600 hover:text-brand-700 font-medium">
                                Forgot password?
                            </Link>
                        </div>

                        <div>
                            <button
                                type="submit"
                                disabled={isSubmitting}
                                className="w-full flex justify-center py-2.5 px-4 border border-transparent rounded-lg shadow-sm text-sm font-medium text-white bg-brand-600 hover:bg-brand-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-brand-500 disabled:opacity-50 transition-colors"
                            >
                                {isSubmitting ? 'Authenticating...' : 'Sign in'}
                            </button>
                        </div>
                    </form>
                </div>
            </div>
        </div>
    );
}
