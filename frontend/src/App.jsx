import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import { AuthProvider, useAuth } from './context/AuthContext';
import { Activity } from 'lucide-react';

// Page Imports
import Login from './pages/Login';
import Patients from './pages/Patients';
import ClinicalDesk from './pages/ClinicalDesk';
import Pharmacy from './pages/Pharmacy';
import Inventory from './pages/Inventory';
import Laboratory from './pages/Laboratory';
import Wards from './pages/Wards';
import AdminDashboard from './pages/AdminDashboard';
import Radiology from './pages/Radiology';
import MedicalHistory from './pages/MedicalHistory';
import Billing from './pages/Billing';
import Portal from './pages/Portal';

// Layout Import
import MainLayout from './components/layouts/MainLayout';

// Super Admin Imports
import SuperAdminLayout from './components/layouts/SuperAdminLayout';
import SuperAdminDashboard from './pages/superadmin/SuperAdminDashboard';
import TenantsManager from './pages/superadmin/TenantsManager';

// Protection Wrapper
const ProtectedRoute = ({ children }) => {
  const { user, loading } = useAuth();
  
  if (loading) {
      return (
          <div className="h-screen w-screen flex items-center justify-center bg-slate-50">
              <Activity className="animate-spin text-brand-600" size={32} />
          </div>
      );
  }
  
  if (!user) {
    return <Navigate to="/login" replace />;
  }
  return children;
};

// SMART ROUTER
const RoleBasedRedirect = () => {
    const { user, loading } = useAuth();
    
    if (loading) return null; 
    if (!user) return <Navigate to="/login" replace />;
    
    switch (user.role) {
        case 'Admin': return <Navigate to="/app/admin" replace />;
        case 'Doctor': return <Navigate to="/app/clinical" replace />;
        case 'Nurse': return <Navigate to="/app/wards" replace />;
        case 'Pharmacist': return <Navigate to="/app/pharmacy" replace />;
        case 'Lab Technician': return <Navigate to="/app/laboratory" replace />;
        case 'Radiologist': return <Navigate to="/app/radiology" replace />;
        case 'Receptionist': return <Navigate to="/app/patients" replace />;
        default: 
            return <Navigate to="/login" replace />;
    }
};

// Temporary Placeholder
const PagePlaceholder = ({ title }) => (
    <div className="bg-white rounded-xl shadow-soft p-6 border border-slate-100">
        <h1 className="text-2xl font-bold text-slate-800">{title}</h1>
        <p className="text-slate-500 mt-2">This module is under construction.</p>
    </div>
);

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Toaster position="top-right" />
        <Routes>
          <Route path="/" element={<Portal />} />
          <Route path="/login" element={<Login />} />

          {/* Super Admin Back-Office (Isolated from Hospital Workspaces) */}
          <Route path="/superadmin" element={<SuperAdminLayout />}>
            <Route index element={<Navigate to="dashboard" replace />} />
            <Route path="dashboard" element={<SuperAdminDashboard />} />
            <Route path="tenants" element={<TenantsManager />} />
            <Route path="*" element={<SuperAdminDashboard />} />
          </Route>

          <Route path="/app" element={<ProtectedRoute><MainLayout /></ProtectedRoute>}>
            <Route index element={<Navigate to="dashboard" replace />} />
            <Route path="dashboard" element={<RoleBasedRedirect />} /> 
            
            <Route path="admin" element={<AdminDashboard />} /> 
            <Route path="patients" element={<Patients />} />
            <Route path="clinical" element={<ClinicalDesk />} />
            <Route path="laboratory" element={<Laboratory />} />
            <Route path="radiology" element={<Radiology />} />
            <Route path="pharmacy" element={<Pharmacy />} />
            <Route path="wards" element={<Wards />} />
            <Route path="inventory" element={<Inventory />} />
            <Route path="medical-history" element={<MedicalHistory />} />
            
            <Route path="appointments" element={<PagePlaceholder title="Appointments" />} />
            <Route path="billing" element={<Billing />} />
          </Route>

          <Route path="*" element={<Navigate to="/app/dashboard" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}