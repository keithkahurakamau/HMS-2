import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import { AuthProvider, useAuth } from './context/AuthContext';
import { Activity } from 'lucide-react'; // Added for the loading spinner

// Page & Layout Imports
import Login from './pages/Login';
import MainLayout from './layouts/MainLayout';
import Patients from './pages/Patients';
import ClinicalDesk from './pages/ClinicalDesk';
import Pharmacy from './pages/Pharmacy';
import Inventory from './pages/Inventory';
import Laboratory from './pages/Laboratory';
import Wards from './pages/Wards';
import AdminDashboard from './pages/AdminDashboard';

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

// 🚨 SMART ROUTER: Directs users to their specific departmental dashboard based on RBAC
const RoleBasedRedirect = () => {
    const { user, loading } = useAuth();
    
    if (loading) return null; // Let ProtectedRoute handle the spinner
    if (!user) return <Navigate to="/login" replace />;
    
    switch (user.role) {
        case 'Admin': return <Navigate to="/admin" replace />;
        case 'Doctor': return <Navigate to="/clinical" replace />;
        case 'Nurse': return <Navigate to="/wards" replace />;
        case 'Pharmacist': return <Navigate to="/pharmacy" replace />;
        case 'Lab Technician': return <Navigate to="/laboratory" replace />;
        case 'Receptionist': return <Navigate to="/patients" replace />;
        default: 
            console.warn(`Unrecognized role: ${user.role}`);
            return <Navigate to="/login" replace />;
    }
};

// Temporary Placeholder for Pages not yet fully built
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
          <Route path="/login" element={<Login />} />

          <Route path="/" element={<ProtectedRoute><MainLayout /></ProtectedRoute>}>
            
            {/* 🚨 Auto-redirect root to the Smart Router */}
            <Route index element={<Navigate to="/dashboard" replace />} />
            <Route path="dashboard" element={<RoleBasedRedirect />} /> 
            
            {/* Core Hospital Modules */}
            <Route path="admin" element={<AdminDashboard />} /> 
            <Route path="patients" element={<Patients />} />
            <Route path="clinical" element={<ClinicalDesk />} />
            <Route path="laboratory" element={<Laboratory />} />
            <Route path="pharmacy" element={<Pharmacy />} />
            <Route path="wards" element={<Wards />} />
            <Route path="inventory" element={<Inventory />} />
            
            {/* Pending Modules */}
            <Route path="appointments" element={<PagePlaceholder title="Appointments" />} />
            <Route path="billing" element={<PagePlaceholder title="Billing & Accounts" />} />
            
          </Route>

          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}