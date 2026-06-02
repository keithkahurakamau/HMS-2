import React, { Suspense, lazy } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ThemeProvider } from './context/ThemeContext';
import { BrandingProvider } from './context/BrandingContext';
import { ModuleProvider } from './context/ModuleContext';
import { PatientProvider } from './context/PatientContext';
import { JourneyProvider } from './context/JourneyContext';
import JourneyOverlay from './components/JourneyOverlay';
import ModuleGuard from './components/ModuleGuard';
import { Activity } from 'lucide-react';
import Seo from './components/Seo';

// Eager imports — public entry points (first paint) + the superadmin guard
// helper, which is read synchronously by SuperAdminProtectedRoute.
import Landing from './pages/Landing';
import Login from './pages/Login';
import SuperAdminLogin, { isSuperAdminAuthenticated } from './pages/superadmin/SuperAdminLogin';

// Lazy page imports — each becomes its own chunk, fetched on first visit.
// Keeps the initial bundle small; authenticated modules load on demand.
const Patients = lazy(() => import('./pages/Patients'));
const ClinicalDesk = lazy(() => import('./pages/ClinicalDesk'));
const Triage = lazy(() => import('./pages/Triage'));
const Pharmacy = lazy(() => import('./pages/Pharmacy'));
const Inventory = lazy(() => import('./pages/Inventory'));
const Laboratory = lazy(() => import('./pages/Laboratory'));
const Wards = lazy(() => import('./pages/Wards'));
const AdminDashboard = lazy(() => import('./pages/AdminDashboard'));
const Radiology = lazy(() => import('./pages/Radiology'));
const MedicalHistory = lazy(() => import('./pages/MedicalHistory'));
const Billing = lazy(() => import('./pages/Billing'));
const Portal = lazy(() => import('./pages/Portal'));
const ForgotPassword = lazy(() => import('./pages/ForgotPassword'));
const ResetPassword = lazy(() => import('./pages/ResetPassword'));
const Appointments = lazy(() => import('./pages/Appointments'));
const PatientPortal = lazy(() => import('./pages/PatientPortal'));
const Messages = lazy(() => import('./pages/Messages'));
const Settings = lazy(() => import('./pages/Settings'));
const MpesaSettings = lazy(() => import('./pages/MpesaSettings'));
const Cheques = lazy(() => import('./pages/Cheques'));
const Support = lazy(() => import('./pages/Support'));
const Branding = lazy(() => import('./pages/Branding'));
const Accounting = lazy(() => import('./pages/Accounting'));

// Layout + superadmin pages — also lazy (the back-office is rarely the first load).
const MainLayout = lazy(() => import('./components/layouts/MainLayout'));
const SuperAdminLayout = lazy(() => import('./components/layouts/SuperAdminLayout'));
const SuperAdminDashboard = lazy(() => import('./pages/superadmin/SuperAdminDashboard'));
const TenantsManager = lazy(() => import('./pages/superadmin/TenantsManager'));
const PlatformBilling = lazy(() => import('./pages/superadmin/PlatformBilling'));
const PlatformSubscriptions = lazy(() => import('./pages/superadmin/PlatformSubscriptions'));
const PaymentsManager = lazy(() => import('./pages/superadmin/PaymentsManager'));
const PlatformSettings = lazy(() => import('./pages/superadmin/PlatformSettings'));
const SuperAdminPatients = lazy(() => import('./pages/superadmin/SuperAdminPatients'));
const UsersManager = lazy(() => import('./pages/superadmin/UsersManager'));
const SupportInbox = lazy(() => import('./pages/superadmin/SupportInbox'));

// Full-screen fallback shown while a lazy route chunk is fetched.
const PageFallback = () => (
  <div className="h-screen w-screen flex items-center justify-center bg-ink-50">
    <Activity className="animate-spin text-brand-600" size={32} aria-label="Loading" />
  </div>
);

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

// Routes that should be indexed by search engines. These pages render their
// own rich <Seo> (title/description/canonical). Every other route is part of
// the authenticated app, the patient portal, the platform back-office, or an
// auth flow — none of which belong in a search index — so RouteMeta stamps
// them noindex. New private routes are covered automatically.
const PUBLIC_PATHS = new Set(['/', '/portal']);

const RouteMeta = () => {
  const { pathname } = useLocation();
  if (PUBLIC_PATHS.has(pathname)) return null;
  return <Seo noindex title="Secure workspace" />;
};

// SMART ROUTER
const RoleBasedRedirect = () => {
    const { user, loading } = useAuth();
    
    if (loading) return null; 
    if (!user) return <Navigate to="/login" replace />;
    
    switch (user.role) {
        case 'Admin': return <Navigate to="/app/admin" replace />;
        case 'Doctor': return <Navigate to="/app/clinical" replace />;
        case 'Nurse': return <Navigate to="/app/triage" replace />;
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
        <JourneyProvider>
          <Toaster position="top-right" />
          <a href="#main-content" className="skip-link">Skip to main content</a>
          {/* User-journey overlay — renders the spotlight + tooltip when a
              module page calls useModuleJourney(). Mounted once at the
              app root so portal target (document.body) is always available. */}
          <JourneyOverlay />
          <RouteMeta />
          <Suspense fallback={<PageFallback />}>
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
            <Route path="users" element={<UsersManager />} />
            <Route path="support" element={<SupportInbox />} />
            <Route path="billing" element={<PlatformBilling />} />
            <Route path="subscriptions" element={<PlatformSubscriptions />} />
            <Route path="payments" element={<PaymentsManager />} />
            <Route path="settings" element={<PlatformSettings />} />
            <Route path="*" element={<SuperAdminDashboard />} />
          </Route>

          <Route path="/app" element={<ProtectedRoute><MainLayout /></ProtectedRoute>}>
            <Route index element={<Navigate to="dashboard" replace />} />
            <Route path="dashboard" element={<RoleBasedRedirect />} /> 
            
            <Route path="admin" element={<AdminDashboard />} />
            <Route path="patients" element={<Patients />} />
            <Route path="triage" element={<ModuleGuard moduleKey="clinical"><Triage /></ModuleGuard>} />
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
            <Route path="mpesa-settings" element={<ModuleGuard moduleKey="payhero"><MpesaSettings /></ModuleGuard>} />
            <Route path="branding" element={<ModuleGuard moduleKey="branding"><Branding /></ModuleGuard>} />
            <Route path="cheques" element={<ModuleGuard moduleKey="cheques"><Cheques /></ModuleGuard>} />
            <Route path="accounting" element={<ModuleGuard moduleKey="accounting"><Accounting /></ModuleGuard>} />
            {/* Support is always-on — never wrap it; that's the escape hatch. */}
            <Route path="support" element={<Support />} />
          </Route>

          {/* Patient self-service portal — no staff auth required */}
          <Route path="/patient" element={<PatientPortal />} />

          <Route path="*" element={<Navigate to="/app/dashboard" replace />} />
          </Routes>
          </Suspense>
        </JourneyProvider>
        </PatientProvider>
        </BrowserRouter>
        </BrandingProvider>
        </ModuleProvider>
      </AuthProvider>
    </ThemeProvider>
  );
}