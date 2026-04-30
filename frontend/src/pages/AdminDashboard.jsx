import React, { useState, useEffect } from 'react';
import { apiClient } from '../api/client';
import { useAuth } from '../context/AuthContext';
import toast from 'react-hot-toast';
import { 
    LayoutDashboard, Users, ShieldAlert, TrendingUp, Activity, 
    AlertCircle, Search, UserPlus, Lock, CheckCircle2,
    X, ShieldCheck, Edit, Key, Save, Tag, PlusCircle
} from 'lucide-react';

export default function AdminDashboard() {
    const { user: currentUser } = useAuth();
    const [activeTab, setActiveTab] = useState('overview'); 
    const [isLoading, setIsLoading] = useState(true);

    const [metrics, setMetrics] = useState({ total_patients: 0, active_admissions: 0, daily_revenue: 0, low_stock_alerts: 0 });
    const [staffList, setStaffList] = useState([]);
    const [auditLogs, setAuditLogs] = useState([]);
    const [pricingList, setPricingList] = useState([]);
    const [searchQuery, setSearchQuery] = useState('');

    const [isStaffModalOpen, setIsStaffModalOpen] = useState(false);
    const [isEditRoleModalOpen, setIsEditRoleModalOpen] = useState(false);
    const [isPricingModalOpen, setIsPricingModalOpen] = useState(false);
    
    const [selectedUser, setSelectedUser] = useState(null);
    const [isSubmitting, setIsSubmitting] = useState(false);

    const [staffForm, setStaffForm] = useState({ email: '', full_name: '', password: '', role: 'Doctor', specialization: '', license_number: '' });
    const [roleEditForm, setRoleEditForm] = useState({ role: '' });
    const [pricingForm, setPricingForm] = useState({ catalog_id: null, test_name: '', category: 'Consultation', description: '', base_price: 0 });

    // --- ROLE PERMISSIONS STATE ---
    const roles = ["Admin", "Doctor", "Nurse", "Pharmacist", "Lab Technician", "Radiologist", "Receptionist"];
    const SYSTEM_PERMISSIONS = [
        "users:manage", "clinical:write", "clinical:read", 
        "patients:read", "patients:write", "history:read", "history:manage",
        "pharmacy:manage", "pharmacy:read", "laboratory:manage", "laboratory:read", 
        "radiology:manage", "radiology:read", "wards:manage", 
        "billing:read", "billing:manage"
    ];
    
    const [selectedRoleForPerms, setSelectedRoleForPerms] = useState('Doctor');
    const [currentRolePerms, setCurrentRolePerms] = useState([]);

    useEffect(() => {
        if (activeTab === 'overview') fetchMetrics();
        if (activeTab === 'staff') fetchStaff();
        if (activeTab === 'audit') fetchAuditLogs();
        if (activeTab === 'pricing') fetchPricing();
        if (activeTab === 'roles') fetchRolePermissions(selectedRoleForPerms);
    }, [activeTab]);

    useEffect(() => {
        if (activeTab === 'roles') {
            fetchRolePermissions(selectedRoleForPerms);
        }
    }, [selectedRoleForPerms]);

    const fetchMetrics = async () => { setIsLoading(true); try { const res = await apiClient.get('/admin/metrics'); setMetrics(res.data); } catch (e) {} finally { setIsLoading(false); } };
    const fetchStaff = async () => { setIsLoading(true); try { const res = await apiClient.get('/admin/users'); setStaffList(res.data || []); } catch (e) { toast.error("Failed to load staff"); } finally { setIsLoading(false); } };
    const fetchAuditLogs = async () => { setIsLoading(true); try { const res = await apiClient.get('/admin/audit-logs'); setAuditLogs(res.data || []); } catch (e) {} finally { setIsLoading(false); } };
    const fetchPricing = async () => { setIsLoading(true); try { const res = await apiClient.get('/admin/pricing'); setPricingList(res.data || []); } catch (e) { toast.error("Failed to load catalog"); } finally { setIsLoading(false); } };
    
    const fetchRolePermissions = async (roleName) => {
        setIsLoading(true);
        try {
            if (roleName === 'Admin') {
                setCurrentRolePerms(SYSTEM_PERMISSIONS); 
            } else {
                const res = await apiClient.get(`/admin/roles/${roleName}/permissions`);
                setCurrentRolePerms(res.data || []);
            }
        } catch (e) {
            toast.error(`Failed to load permissions for ${roleName}.`);
            setCurrentRolePerms([]);
        } finally {
            setIsLoading(false);
        }
    };

    const handleRegisterStaff = async (e) => {
        e.preventDefault();
        setIsSubmitting(true);
        try {
            await apiClient.post('/admin/users', staffForm);
            toast.success("Staff member registered successfully.");
            setIsStaffModalOpen(false);
            fetchStaff();
        } catch (error) { toast.error(error.response?.data?.detail || "Registration failed."); } finally { setIsSubmitting(false); }
    };

    const handleSavePricing = async (e) => {
        e.preventDefault();
        setIsSubmitting(true);
        try {
            if (pricingForm.catalog_id) {
                await apiClient.put(`/admin/pricing/${pricingForm.catalog_id}`, pricingForm);
                toast.success("Service package updated.");
            } else {
                await apiClient.post('/admin/pricing', pricingForm);
                toast.success("New service package created.");
            }
            setIsPricingModalOpen(false);
            fetchPricing();
        } catch (error) { toast.error(error.response?.data?.detail || "Failed to save pricing."); } finally { setIsSubmitting(false); }
    };

    const handleToggleAccountStatus = async (userId, currentStatus) => {
        try {
            await apiClient.patch(`/admin/users/${userId}/status`, { is_active: !currentStatus });
            toast.success(`Account ${!currentStatus ? 'activated' : 'locked'}.`);
            fetchStaff();
        } catch (error) { toast.error("Failed to update account status."); }
    };

    const handleUpdateRole = async (e) => {
        e.preventDefault();
        setIsSubmitting(true);
        try {
            await apiClient.patch(`/admin/users/${selectedUser.user_id}/role`, { role: roleEditForm.role });
            toast.success(`${selectedUser.full_name}'s access updated to ${roleEditForm.role}.`);
            setIsEditRoleModalOpen(false);
            fetchStaff();
        } catch (error) {
            toast.error(error.response?.data?.detail || "Failed to update role.");
        } finally {
            setIsSubmitting(false);
        }
    };

    const handleSavePermissions = async () => {
        setIsSubmitting(true);
        try {
            await apiClient.put(`/admin/roles/${selectedRoleForPerms}/permissions`, { permissions: currentRolePerms });
            toast.success(`${selectedRoleForPerms} permissions updated successfully!`);
        } catch (error) {
            toast.error(error.response?.data?.detail || "Failed to update permissions.");
        } finally {
            setIsSubmitting(false);
        }
    };

    const togglePermission = (perm) => {
        if (currentRolePerms.includes(perm)) {
            setCurrentRolePerms(currentRolePerms.filter(p => p !== perm));
        } else {
            setCurrentRolePerms([...currentRolePerms, perm]);
        }
    };

    const openEditRoleModal = (user) => {
        setSelectedUser(user);
        setRoleEditForm({ role: user.role });
        setIsEditRoleModalOpen(true);
    };

    const openPricingModal = (item = null) => {
        if (item) {
            setPricingForm({ catalog_id: item.catalog_id, test_name: item.test_name, category: item.category, description: item.default_specimen_type || '', base_price: item.base_price });
        } else {
            setPricingForm({ catalog_id: null, test_name: '', category: 'Consultation', description: '', base_price: 0 });
        }
        setIsPricingModalOpen(true);
    };

    const filteredStaff = staffList.filter(user => user.full_name.toLowerCase().includes(searchQuery.toLowerCase()) || user.email.toLowerCase().includes(searchQuery.toLowerCase()));
    const filteredPricing = pricingList.filter(item => item.test_name.toLowerCase().includes(searchQuery.toLowerCase()) || item.category.toLowerCase().includes(searchQuery.toLowerCase()));

    return (
        <div className="h-[calc(100vh-8rem)] flex flex-col gap-4">
            
            {/* HEADER & TABS */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-2 shadow-sm flex flex-col md:flex-row items-center justify-between shrink-0 gap-2">
                <div className="flex flex-wrap bg-slate-800 p-1 rounded-lg w-full max-w-4xl gap-1">
                    <button onClick={() => setActiveTab('overview')} className={`flex-1 flex items-center justify-center gap-2 py-2 px-3 rounded-md text-sm font-bold transition-all ${activeTab === 'overview' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-300 hover:text-white'}`}>
                        <LayoutDashboard size={16} /> Overview
                    </button>
                    <button onClick={() => setActiveTab('staff')} className={`flex-1 flex items-center justify-center gap-2 py-2 px-3 rounded-md text-sm font-bold transition-all ${activeTab === 'staff' ? 'bg-brand-500 text-white shadow-sm' : 'text-slate-300 hover:text-white'}`}>
                        <Users size={16} /> Directory
                    </button>
                    <button onClick={() => setActiveTab('pricing')} className={`flex-1 flex items-center justify-center gap-2 py-2 px-3 rounded-md text-sm font-bold transition-all ${activeTab === 'pricing' ? 'bg-green-500 text-white shadow-sm' : 'text-slate-300 hover:text-white'}`}>
                        <Tag size={16} /> Pricing & Catalog
                    </button>
                    <button onClick={() => setActiveTab('roles')} className={`flex-1 flex items-center justify-center gap-2 py-2 px-3 rounded-md text-sm font-bold transition-all ${activeTab === 'roles' ? 'bg-accent-600 text-white shadow-sm' : 'text-slate-300 hover:text-white'}`}>
                        <Key size={16} /> Permissions
                    </button>
                    <button onClick={() => setActiveTab('audit')} className={`flex-1 flex items-center justify-center gap-2 py-2 px-3 rounded-md text-sm font-bold transition-all ${activeTab === 'audit' ? 'bg-red-500 text-white shadow-sm' : 'text-slate-300 hover:text-white'}`}>
                        <ShieldAlert size={16} /> Audit
                    </button>
                </div>
                <div className="text-right px-4 text-sm font-bold text-slate-400 flex items-center gap-2 shrink-0">
                    <ShieldCheck size={18} className="text-green-400"/> Root Access Active
                </div>
            </div>

            {/* TAB 1: SYSTEM OVERVIEW */}
            {activeTab === 'overview' && (
                <div className="space-y-6 overflow-y-auto custom-scrollbar pr-2">
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                        <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm flex flex-col">
                            <div className="flex justify-between items-start mb-4">
                                <div className="w-12 h-12 bg-blue-50 text-blue-600 rounded-xl flex items-center justify-center"><Users size={24} /></div>
                                <span className="bg-green-100 text-green-700 text-xs font-bold px-2 py-1 rounded-full">Live</span>
                            </div>
                            <h3 className="text-slate-500 text-sm font-bold uppercase tracking-wider mb-1">Total Registered Patients</h3>
                            <p className="text-3xl font-black text-slate-900">{metrics.total_patients.toLocaleString()}</p>
                        </div>
                        <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm flex flex-col">
                            <div className="flex justify-between items-start mb-4">
                                <div className="w-12 h-12 bg-brand-50 text-brand-600 rounded-xl flex items-center justify-center"><TrendingUp size={24} /></div>
                            </div>
                            <h3 className="text-slate-500 text-sm font-bold uppercase tracking-wider mb-1">Today's Billed Revenue</h3>
                            <p className="text-3xl font-black text-slate-900">KES {metrics.daily_revenue.toLocaleString()}</p>
                        </div>
                        <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm flex flex-col">
                            <div className="flex justify-between items-start mb-4">
                                <div className="w-12 h-12 bg-purple-50 text-purple-600 rounded-xl flex items-center justify-center"><Activity size={24} /></div>
                            </div>
                            <h3 className="text-slate-500 text-sm font-bold uppercase tracking-wider mb-1">Active Inpatient Admissions</h3>
                            <p className="text-3xl font-black text-slate-900">{metrics.active_admissions}</p>
                        </div>
                        <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm flex flex-col">
                            <div className="flex justify-between items-start mb-4">
                                <div className="w-12 h-12 bg-orange-50 text-orange-600 rounded-xl flex items-center justify-center"><AlertCircle size={24} /></div>
                                {metrics.low_stock_alerts > 0 && <span className="bg-red-100 text-red-700 text-xs font-bold px-2 py-1 rounded-full animate-pulse">Action Required</span>}
                            </div>
                            <h3 className="text-slate-500 text-sm font-bold uppercase tracking-wider mb-1">Low Stock Alerts</h3>
                            <p className="text-3xl font-black text-slate-900">{metrics.low_stock_alerts}</p>
                        </div>
                    </div>
                </div>
            )}

            {/* TAB 2: STAFF DIRECTORY */}
            {activeTab === 'staff' && (
                <div className="flex-1 bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden flex flex-col">
                    <div className="p-4 border-b border-slate-100 flex flex-col sm:flex-row items-center justify-between gap-4 bg-slate-50">
                        <div className="relative w-full max-w-md">
                            <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                            <input 
                                type="text" placeholder="Search staff by name or email..." 
                                value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)}
                                className="w-full pl-10 pr-4 py-2.5 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-500 text-sm transition-all" 
                            />
                        </div>
                        <button onClick={() => setIsStaffModalOpen(true)} className="flex items-center gap-2 px-5 py-2.5 bg-brand-600 text-white rounded-lg text-sm font-bold hover:bg-brand-700 shadow-sm transition-colors">
                            <UserPlus size={18} /> Provision New Account
                        </button>
                    </div>

                    <div className="flex-1 overflow-auto">
                        <table className="w-full text-left text-sm text-slate-600">
                            <thead className="bg-white text-slate-500 text-xs uppercase font-bold border-b border-slate-200 sticky top-0">
                                <tr>
                                    <th className="px-6 py-4">Staff Member</th>
                                    <th className="px-6 py-4">Role & Access</th>
                                    <th className="px-6 py-4">License / Specs</th>
                                    <th className="px-6 py-4">Status</th>
                                    <th className="px-6 py-4 text-right">Security & RBAC</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100">
                                {isLoading ? (
                                    <tr><td colSpan="5" className="px-6 py-12 text-center text-slate-400"><Activity className="animate-spin mx-auto mb-2" /> Loading directory...</td></tr>
                                ) : filteredStaff.length === 0 ? (
                                    <tr><td colSpan="5" className="px-6 py-12 text-center text-slate-400">No staff members found.</td></tr>
                                ) : (
                                    filteredStaff.map((user) => {
                                        const isCurrentUser = user.email === currentUser?.email;
                                        return (
                                            <tr key={user.user_id} className="hover:bg-slate-50 transition-colors">
                                                <td className="px-6 py-4">
                                                    <div className="font-bold text-slate-900">{user.full_name}</div>
                                                    <div className="text-xs text-slate-500 mt-0.5">{user.email}</div>
                                                </td>
                                                <td className="px-6 py-4">
                                                    <span className={`px-2.5 py-1 rounded text-xs font-bold ${user.role === 'Admin' ? 'bg-red-100 text-red-700' : 'bg-slate-100 text-slate-700'}`}>
                                                        {user.role}
                                                    </span>
                                                </td>
                                                <td className="px-6 py-4 text-xs">
                                                    <div className="font-semibold text-slate-700">{user.specialization || 'N/A'}</div>
                                                    <div className="text-slate-400">{user.license_number || 'N/A'}</div>
                                                </td>
                                                <td className="px-6 py-4">
                                                    {user.is_active ? (
                                                        <span className="flex items-center gap-1 text-green-600 text-xs font-bold"><CheckCircle2 size={14}/> Active</span>
                                                    ) : (
                                                        <span className="flex items-center gap-1 text-red-600 text-xs font-bold"><Lock size={14}/> Locked</span>
                                                    )}
                                                </td>
                                                <td className="px-6 py-4 text-right flex justify-end gap-2">
                                                    <button 
                                                        onClick={() => openEditRoleModal(user)}
                                                        className="text-xs font-bold px-3 py-1.5 rounded border border-slate-200 text-brand-600 hover:bg-brand-50 hover:border-brand-200 transition-colors flex items-center gap-1"
                                                    >
                                                        <Edit size={12}/> Edit Access
                                                    </button>
                                                    <button 
                                                        onClick={() => handleToggleAccountStatus(user.user_id, user.is_active)}
                                                        disabled={isCurrentUser}
                                                        className={`text-xs font-bold px-3 py-1.5 rounded border transition-colors ${
                                                            isCurrentUser 
                                                            ? 'border-slate-100 text-slate-300 bg-slate-50 cursor-not-allowed' 
                                                            : user.is_active 
                                                                ? 'border-slate-200 text-slate-600 hover:bg-red-50 hover:text-red-600 hover:border-red-200' 
                                                                : 'bg-slate-800 text-white hover:bg-slate-900'
                                                        }`}
                                                    >
                                                        {isCurrentUser ? 'Current User' : user.is_active ? 'Lock Account' : 'Unlock Account'}
                                                    </button>
                                                </td>
                                            </tr>
                                        );
                                    })
                                )}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {/* TAB 3: MASTER PRICING CATALOG */}
            {activeTab === 'pricing' && (
                <div className="flex-1 bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden flex flex-col">
                    <div className="p-4 border-b border-slate-100 flex flex-col sm:flex-row items-center justify-between gap-4 bg-slate-50">
                        <div className="relative w-full max-w-md">
                            <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                            <input 
                                type="text" placeholder="Search services by name or category..." 
                                value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)}
                                className="w-full pl-10 pr-4 py-2.5 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-500 text-sm transition-all" 
                            />
                        </div>
                        <button onClick={() => openPricingModal()} className="flex items-center gap-2 px-5 py-2.5 bg-green-600 text-white rounded-lg text-sm font-bold hover:bg-green-700 shadow-sm transition-colors">
                            <PlusCircle size={18} /> Add Service Package
                        </button>
                    </div>

                    <div className="flex-1 overflow-auto">
                        <table className="w-full text-left text-sm text-slate-600">
                            <thead className="bg-white text-slate-500 text-xs uppercase font-bold border-b border-slate-200 sticky top-0">
                                <tr>
                                    <th className="px-6 py-4">Service / Test Name</th>
                                    <th className="px-6 py-4">Category</th>
                                    <th className="px-6 py-4">Description / Use Case</th>
                                    <th className="px-6 py-4">Base Price (KES)</th>
                                    <th className="px-6 py-4 text-right">Actions</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100">
                                {isLoading ? (
                                    <tr><td colSpan="5" className="px-6 py-12 text-center text-slate-400"><Activity className="animate-spin mx-auto mb-2" /> Loading pricing catalog...</td></tr>
                                ) : filteredPricing.length === 0 ? (
                                    <tr><td colSpan="5" className="px-6 py-12 text-center text-slate-400">No services found in the catalog.</td></tr>
                                ) : (
                                    filteredPricing.map((item) => (
                                        <tr key={item.catalog_id} className="hover:bg-slate-50 transition-colors">
                                            <td className="px-6 py-4 font-bold text-slate-900">{item.test_name}</td>
                                            <td className="px-6 py-4">
                                                <span className="px-2.5 py-1 bg-slate-100 text-slate-700 rounded text-xs font-bold">
                                                    {item.category}
                                                </span>
                                            </td>
                                            <td className="px-6 py-4 text-xs text-slate-500 max-w-xs truncate">
                                                {item.default_specimen_type || 'No description provided'}
                                            </td>
                                            <td className="px-6 py-4 font-black text-green-700">
                                                KES {parseFloat(item.base_price).toLocaleString()}
                                            </td>
                                            <td className="px-6 py-4 text-right">
                                                <button 
                                                    onClick={() => openPricingModal(item)}
                                                    className="text-xs font-bold px-3 py-1.5 rounded border border-slate-200 text-brand-600 hover:bg-brand-50 hover:border-brand-200 transition-colors flex items-center gap-1 ml-auto"
                                                >
                                                    <Edit size={12}/> Edit Pricing
                                                </button>
                                            </td>
                                        </tr>
                                    ))
                                )}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {/* TAB 4: ROLE PERMISSIONS MATRIX */}
            {activeTab === 'roles' && (
                <div className="flex-1 flex flex-col md:flex-row gap-4 overflow-hidden">
                    {/* Left Pane: Role Selector */}
                    <div className="w-full md:w-64 bg-white border border-slate-200 rounded-xl shadow-sm flex flex-col shrink-0">
                        <div className="p-4 border-b border-slate-100 bg-slate-50">
                            <h2 className="font-bold text-slate-800">System Roles</h2>
                        </div>
                        <div className="flex-1 overflow-y-auto p-2 space-y-1 custom-scrollbar">
                            {roles.map(r => (
                                <button 
                                    key={r}
                                    onClick={() => setSelectedRoleForPerms(r)}
                                    className={`w-full text-left px-4 py-3 rounded-lg text-sm font-bold transition-colors ${selectedRoleForPerms === r ? 'bg-accent-50 text-accent-700 border border-accent-200' : 'text-slate-600 hover:bg-slate-50 border border-transparent'}`}
                                >
                                    {r}
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Right Pane: Permission Checkboxes */}
                    <div className="flex-1 bg-white border border-slate-200 rounded-xl shadow-sm flex flex-col overflow-hidden">
                        <div className="p-4 border-b border-slate-100 bg-slate-50 flex justify-between items-center">
                            <div>
                                <h2 className="font-bold text-slate-800">Permissions: <span className="text-accent-600">{selectedRoleForPerms}</span></h2>
                                <p className="text-xs text-slate-500 mt-1">Select the exact database operations this role is authorized to perform.</p>
                            </div>
                            <button onClick={handleSavePermissions} disabled={isSubmitting || selectedRoleForPerms === 'Admin'} className="flex items-center gap-2 px-4 py-2 bg-brand-600 text-white rounded-lg text-sm font-bold hover:bg-brand-700 shadow-sm transition-colors disabled:opacity-50">
                                {isSubmitting ? <Activity className="animate-spin" size={16}/> : <Save size={16} />}
                                Save Changes
                            </button>
                        </div>
                        <div className="flex-1 overflow-y-auto p-6 custom-scrollbar">
                            {selectedRoleForPerms === 'Admin' && (
                                <div className="mb-6 p-4 bg-red-50 border border-red-200 text-red-700 rounded-lg text-sm font-bold flex items-center gap-3">
                                    <ShieldAlert size={20} />
                                    Admin privileges are hardcoded to wildcard ("*") and cannot be restricted.
                                </div>
                            )}

                            {isLoading ? (
                                <div className="flex flex-col items-center justify-center py-12 text-slate-400">
                                    <Activity className="animate-spin mb-2 text-brand-500" size={24}/>
                                    Loading permissions...
                                </div>
                            ) : (
                                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                                    {SYSTEM_PERMISSIONS.map(perm => (
                                        <label key={perm} className={`flex items-center gap-3 p-4 border rounded-xl cursor-pointer transition-colors ${currentRolePerms.includes(perm) ? 'border-brand-500 bg-brand-50/50' : 'border-slate-200 bg-white hover:bg-slate-50'} ${selectedRoleForPerms === 'Admin' ? 'opacity-60 cursor-not-allowed' : ''}`}>
                                            <input 
                                                type="checkbox" 
                                                checked={currentRolePerms.includes(perm) || selectedRoleForPerms === 'Admin'}
                                                onChange={() => togglePermission(perm)}
                                                disabled={selectedRoleForPerms === 'Admin'}
                                                className="w-5 h-5 text-brand-600 rounded border-slate-300 focus:ring-brand-500"
                                            />
                                            <div className="flex-1">
                                                <div className="text-sm font-bold text-slate-800">{perm.split(':')[0].toUpperCase()}</div>
                                                <div className="text-xs text-slate-500 capitalize">{perm.split(':')[1]} Access</div>
                                            </div>
                                        </label>
                                    ))}
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            )}

            {/* TAB 5: SYSTEM AUDIT LOGS */}
            {activeTab === 'audit' && (
                <div className="flex-1 bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden flex flex-col">
                    <div className="p-4 border-b border-slate-100 bg-slate-50">
                        <h2 className="font-bold text-slate-800 flex items-center gap-2"><ShieldAlert className="text-red-500" size={20}/> Immutable Security Ledger</h2>
                        <p className="text-xs text-slate-500 mt-1">Tracks all critical CREATE, UPDATE, and DELETE operations across the hospital infrastructure.</p>
                    </div>
                    <div className="flex-1 overflow-auto">
                        <table className="w-full text-left text-sm text-slate-600">
                            <thead className="bg-white text-slate-500 text-xs uppercase font-bold border-b border-slate-200 sticky top-0">
                                <tr>
                                    <th className="px-6 py-3">Timestamp (UTC)</th>
                                    <th className="px-6 py-3">Actor (User ID)</th>
                                    <th className="px-6 py-3">Operation</th>
                                    <th className="px-6 py-3">Entity & ID</th>
                                    <th className="px-6 py-3 w-1/3">Data Snapshot</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100 font-mono text-xs">
                                {isLoading ? (
                                    <tr><td colSpan="5" className="px-6 py-12 text-center text-slate-400 font-sans"><Activity className="animate-spin mx-auto mb-2" /> Decrypting logs...</td></tr>
                                ) : auditLogs.length === 0 ? (
                                    <tr><td colSpan="5" className="px-6 py-12 text-center text-slate-400 font-sans">No audit trails found.</td></tr>
                                ) : (
                                    auditLogs.map((log) => (
                                        <tr key={log.log_id} className="hover:bg-slate-50">
                                            <td className="px-6 py-3 text-slate-500">{new Date(log.timestamp).toLocaleString()}</td>
                                            <td className="px-6 py-3 font-bold text-slate-800">{log.user_id || 'SYSTEM'}</td>
                                            <td className="px-6 py-3">
                                                <span className={`px-2 py-0.5 rounded font-bold ${log.action === 'CREATE' ? 'bg-green-100 text-green-700' : log.action === 'DELETE' ? 'bg-red-100 text-red-700' : 'bg-blue-100 text-blue-700'}`}>
                                                    {log.action}
                                                </span>
                                            </td>
                                            <td className="px-6 py-3 text-brand-700 font-bold">{log.entity_type} [{log.entity_id}]</td>
                                            <td className="px-6 py-3 text-slate-400 truncate max-w-xs">{JSON.stringify(log.new_value || log.old_value)}</td>
                                        </tr>
                                    ))
                                )}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {/* --- ADD STAFF MODAL --- */}
            {isStaffModalOpen && (
                <div className="fixed inset-0 z-50 overflow-hidden flex justify-end">
                    <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm" onClick={() => setIsStaffModalOpen(false)}></div>
                    <div className="relative w-full max-w-md bg-white h-full shadow-2xl flex flex-col animate-in slide-in-from-right">
                        <div className="p-6 border-b border-slate-100 bg-slate-900 text-white shrink-0 flex justify-between items-center">
                            <div>
                                <h2 className="text-xl font-bold flex items-center gap-2"><UserPlus size={24} className="text-brand-400" /> Provision Account</h2>
                                <p className="text-sm text-slate-400 mt-1">Create a new staff identity & assign RBAC roles.</p>
                            </div>
                            <button onClick={() => setIsStaffModalOpen(false)} className="text-slate-400 hover:text-white"><X size={24}/></button>
                        </div>
                        <div className="flex-1 overflow-y-auto p-6 space-y-6 bg-slate-50">
                            <form id="staffForm" onSubmit={handleRegisterStaff} className="space-y-4">
                                <div><label className="block text-xs font-bold text-slate-700 mb-1.5">Full Name</label><input required type="text" value={staffForm.full_name} onChange={e => setStaffForm({...staffForm, full_name: e.target.value})} className="w-full px-4 py-2.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none" /></div>
                                <div><label className="block text-xs font-bold text-slate-700 mb-1.5">Email Address (Login ID)</label><input required type="email" value={staffForm.email} onChange={e => setStaffForm({...staffForm, email: e.target.value})} className="w-full px-4 py-2.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none" /></div>
                                <div><label className="block text-xs font-bold text-slate-700 mb-1.5">Temporary Password</label><input required type="password" value={staffForm.password} onChange={e => setStaffForm({...staffForm, password: e.target.value})} className="w-full px-4 py-2.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none" /></div>
                                <hr className="my-6 border-slate-200" />
                                <div>
                                    <label className="block text-xs font-bold text-slate-700 mb-1.5">System Role (RBAC)</label>
                                    <select required value={staffForm.role} onChange={e => setStaffForm({...staffForm, role: e.target.value})} className="w-full px-4 py-2.5 border border-slate-200 rounded-lg text-sm font-bold text-brand-700 focus:ring-2 focus:ring-brand-500 outline-none">
                                        {roles.map(r => <option key={r} value={r}>{r}</option>)}
                                    </select>
                                </div>
                            </form>
                        </div>
                        <div className="p-6 border-t border-slate-200 bg-white flex gap-3 shrink-0">
                            <button type="submit" form="staffForm" disabled={isSubmitting} className="w-full bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white py-3 rounded-lg font-bold shadow-sm flex items-center justify-center gap-2 transition-colors">
                                {isSubmitting ? 'Provisioning...' : 'Create Account & Grant Access'}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* --- PRICING & CATALOG MODAL --- */}
            {isPricingModalOpen && (
                <div className="fixed inset-0 z-50 flex items-center justify-center">
                    <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm" onClick={() => setIsPricingModalOpen(false)}></div>
                    <div className="relative w-full max-w-md bg-white rounded-2xl shadow-2xl flex flex-col overflow-hidden animate-in fade-in zoom-in-95">
                        <div className="p-6 border-b border-slate-100 bg-slate-50 flex justify-between items-center">
                            <div>
                                <h2 className="text-lg font-bold text-slate-900">{pricingForm.catalog_id ? "Edit Service Package" : "Create Service Package"}</h2>
                                <p className="text-xs text-slate-500 mt-1">Configure pricing for Billing module.</p>
                            </div>
                            <button onClick={() => setIsPricingModalOpen(false)} className="text-slate-400 hover:text-slate-700"><X size={20}/></button>
                        </div>
                        <div className="p-6">
                            <form id="pricingForm" onSubmit={handleSavePricing} className="space-y-4">
                                <div>
                                    <label className="block text-xs font-bold text-slate-700 mb-1.5">Service / Test Name <span className="text-red-500">*</span></label>
                                    <input required type="text" value={pricingForm.test_name} onChange={e => setPricingForm({ ...pricingForm, test_name: e.target.value })} placeholder="e.g. Initial Consultation" className="w-full px-4 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none" />
                                </div>
                                <div>
                                    <label className="block text-xs font-bold text-slate-700 mb-1.5">Category <span className="text-red-500">*</span></label>
                                    <select required value={pricingForm.category} onChange={e => setPricingForm({ ...pricingForm, category: e.target.value })} className="w-full px-4 py-2 border border-slate-200 rounded-lg text-sm font-bold focus:ring-2 focus:ring-brand-500 outline-none bg-white">
                                        <option>Consultation</option>
                                        <option>Laboratory</option>
                                        <option>Radiology</option>
                                        <option>Procedure</option>
                                        <option>General Service</option>
                                    </select>
                                </div>
                                <div>
                                    <label className="block text-xs font-bold text-slate-700 mb-1.5">Description / Use Case</label>
                                    <textarea value={pricingForm.description} onChange={e => setPricingForm({ ...pricingForm, description: e.target.value })} rows="2" placeholder="Describe the purpose of this package..." className="w-full px-4 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none resize-none"></textarea>
                                </div>
                                <div>
                                    <label className="block text-xs font-bold text-slate-700 mb-1.5">Base Price (KES) <span className="text-red-500">*</span></label>
                                    <input required type="number" min="0" step="0.01" value={pricingForm.base_price} onChange={e => setPricingForm({ ...pricingForm, base_price: e.target.value })} className="w-full px-4 py-2 border border-slate-200 rounded-lg text-sm font-black text-green-700 focus:ring-2 focus:ring-brand-500 outline-none" />
                                </div>
                            </form>
                        </div>
                        <div className="p-4 border-t border-slate-100 bg-slate-50 flex justify-end gap-3">
                            <button onClick={() => setIsPricingModalOpen(false)} className="px-4 py-2 text-sm font-bold text-slate-600 hover:bg-slate-200 rounded-lg transition-colors">Cancel</button>
                            <button type="submit" form="pricingForm" disabled={isSubmitting} className="px-6 py-2 bg-brand-600 text-white text-sm font-bold rounded-lg shadow-sm hover:bg-brand-700 disabled:opacity-50 transition-colors flex items-center gap-2">
                                {isSubmitting ? <Activity className="animate-spin" size={16}/> : <Save size={16}/>}
                                Save Package
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* --- EDIT ROLE MODAL --- */}
            {isEditRoleModalOpen && selectedUser && (
                <div className="fixed inset-0 z-50 flex items-center justify-center">
                    <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm" onClick={() => setIsEditRoleModalOpen(false)}></div>
                    <div className="relative w-full max-w-sm bg-white rounded-2xl shadow-2xl flex flex-col overflow-hidden animate-in fade-in zoom-in-95">
                        <div className="p-6 border-b border-slate-100 bg-slate-50 flex justify-between items-center">
                            <div>
                                <h2 className="text-lg font-bold text-slate-900">Edit RBAC Access</h2>
                                <p className="text-xs text-slate-500 mt-1">Modifying roles for {selectedUser.full_name}</p>
                            </div>
                            <button onClick={() => setIsEditRoleModalOpen(false)} className="text-slate-400 hover:text-slate-700"><X size={20}/></button>
                        </div>
                        <div className="p-6">
                            <form id="editRoleForm" onSubmit={handleUpdateRole} className="space-y-4">
                                <div>
                                    <label className="block text-xs font-bold text-slate-700 mb-1.5">New Security Role</label>
                                    <select required value={roleEditForm.role} onChange={e => setRoleEditForm({ role: e.target.value })} className="w-full px-4 py-2.5 border border-slate-200 rounded-lg text-sm font-bold text-brand-700 focus:ring-2 focus:ring-brand-500 outline-none">
                                        {roles.map(r => <option key={r} value={r}>{r}</option>)}
                                    </select>
                                </div>
                            </form>
                        </div>
                        <div className="p-4 border-t border-slate-100 bg-slate-50 flex justify-end gap-3">
                            <button onClick={() => setIsEditRoleModalOpen(false)} className="px-4 py-2 text-sm font-bold text-slate-600 hover:bg-slate-200 rounded-lg transition-colors">Cancel</button>
                            <button type="submit" form="editRoleForm" disabled={isSubmitting} className="px-6 py-2 bg-brand-600 text-white text-sm font-bold rounded-lg shadow-sm hover:bg-brand-700 disabled:opacity-50 transition-colors flex items-center gap-2">
                                {isSubmitting ? <Activity className="animate-spin" size={16}/> : <ShieldCheck size={16}/>}
                                Update Access
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}