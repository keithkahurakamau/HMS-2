import React from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ThemeProvider } from './context/ThemeContext';
import { BrandingProvider } from './context/BrandingContext';
import { ModuleProvider } from './context/ModuleContext';
import { PatientProvider } from './context/PatientContext';
import ModuleGuard from './components/ModuleGuard';
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
import ForgotPassword from './pages/ForgotPassword';
import ResetPassword from './pages/ResetPassword';
import Appointments from './pages/Appointments';
import PatientPortal from './pages/PatientPortal';
import Messages from './pages/Messages';
import Settings from './pages/Settings';
import Cheques from './pages/Cheques';
import Support from './pages/Support';
import Landing from './pages/Landing';
import Branding from './pages/Branding';

// Layout Import
import MainLayout from './components/layouts/MainLayout';

// Super Admin Imports
import SuperAdminLayout from './components/layouts/SuperAdminLayout';
import SuperAdminDashboard from './pages/superadmin/SuperAdminDashboard';
import TenantsManager from './pages/superadmin/TenantsManager';
import PlatformBilling from './pages/superadmin/PlatformBilling';
import PlatformSettings from './pages/superadmin/PlatformSettings';
import SuperAdminPatients from './pages/superadmin/SuperAdminPatients';
import SupportInbox from './pages/superadmin/SupportInbox';
import SuperAdminLogin, { isSuperAdminAuthenticated } from './pages/superadmin/SuperAdminLogin';

// Protection Wrapper
const ProtectedRoute = ({ children }) => {
  const { user, loading } = useAuth();
  
  if (loading) {
      return (
          <div className="h-screen w-screen flex items-center justify-center bg-ink-50">
              <Activity className="animate-spin text-brand-600" size={32} aria-label="Loading" />
          </div>
      );
  }
  
  if (!user) {
    return <Navigate to="/login" replace />;
  }
  return children;
};

// Superadmin route guard — checks for the platform-level token in localStorage.
// On miss, redirect to /superadmin/login while preserving the original path so
// the user lands where they intended after authenticating.
const SuperAdminProtectedRoute = ({ children }) => {
  const location = useLocation();
  if (!isSuperAdminAuthenticated()) {
    return <Navigate to="/superadmin/login" replace state={{ from: location }} />;
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
            // Custom roles (admin-created) don't have a baked-in landing page,
            // so we drop them on Messages — every role gets messaging:read by
            // default, so the page is guaranteed to render something useful.
            return <Navigate to="/app/messages" replace />;
    }
};

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <ModuleProvider>
        <BrandingProvider>
        <BrowserRouter>
        <PatientProvider>
          <Toaster position="top-right" />
          <a href="#main-content" className="skip-link">Skip to main content</a>
          <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/portal" element={<Portal />} />
          <Route path="/login" element={<Login />} />
          <Route path="/forgot-password" element={<ForgotPassword />} />
          <Route path="/reset-password" element={<ResetPassword />} />

          {/* Super Admin Back-Office (Isolated from Hospital Workspaces) */}
          <Route path="/superadmin/login" element={<SuperAdminLogin />} />
          <Route path="/superadmin" element={<SuperAdminProtectedRoute><SuperAdminLayout /></SuperAdminProtectedRoute>}>
            <Route index element={<Navigate to="dashboard" replace />} />
            <Route path="dashboard" element={<SuperAdminDashboard />} />
            <Route path="tenants" element={<TenantsManager />} />
            <Route path="patients" element={<SuperAdminPatients />} />
            <Route path="support" element={<SupportInbox />} />
            <Route path="billing" element={<PlatformBilling />} />
            <Route path="settings" element={<PlatformSettings />} />
            <Route path="*" element={<SuperAdminDashboard />} />
          </Route>

          <Route path="/app" element={<ProtectedRoute><MainLayout /></ProtectedRoute>}>
            <Route index element={<Navigate to="dashboard" replace />} />
            <Route path="dashboard" element={<RoleBasedRedirect />} /> 
            
            <Route path="admin" element={<AdminDashboard />} />
            <Route path="patients" element={<Patients />} />
            <Route path="clinical" element={<ModuleGuard moduleKey="clinical"><ClinicalDesk /></ModuleGuard>} />
            <Route path="laboratory" element={<ModuleGuard moduleKey="laboratory"><Laboratory /></ModuleGuard>} />
            <Route path="radiology" element={<ModuleGuard moduleKey="radiology"><Radiology /></ModuleGuard>} />
            <Route path="pharmacy" element={<ModuleGuard moduleKey="pharmacy"><Pharmacy /></ModuleGuard>} />
            <Route path="wards" element={<ModuleGuard moduleKey="wards"><Wards /></ModuleGuard>} />
            <Route path="inventory" element={<ModuleGuard moduleKey="inventory"><Inventory /></ModuleGuard>} />
            <Route path="medical-history" element={<ModuleGuard moduleKey="medical_history"><MedicalHistory /></ModuleGuard>} />

            <Route path="appointments" element={<Appointments />} />
            <Route path="billing" element={<ModuleGuard moduleKey="billing"><Billing /></ModuleGuard>} />
            <Route path="messages" element={<Messages />} />
            <Route path="settings" element={<Settings />} />
            <Route path="branding" element={<ModuleGuard moduleKey="branding"><Branding /></ModuleGuard>} />
            <Route path="cheques" element={<ModuleGuard moduleKey="cheques"><Cheques /></ModuleGuard>} />
            {/* Support is always-on — never wrap it; that's the escape hatch. */}
            <Route path="support" element={<Support />} />
          </Route>

          {/* Patient self-service portal — no staff auth required */}
          <Route path="/patient" element={<PatientPortal />} />

          <Route path="*" element={<Navigate to="/app/dashboard" replace />} />
          </Routes>
        </PatientProvider>
        </BrowserRouter>
        </BrandingProvider>
        </ModuleProvider>
      </AuthProvider>
    </ThemeProvider>
  );
}