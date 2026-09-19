import { BrowserRouter as Router, Routes, Route, Navigate, Outlet } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';

import Login from './pages/Login';
import ForgotPassword from './pages/ForgotPassword';
import ResetPassword from './pages/ResetPassword';
import VerifyEmail from './pages/VerifyEmail';
import Landing from './pages/public/Landing';
import About from './pages/public/About';
import Contact from './pages/public/Contact';
import Pricing from './pages/public/Pricing';
import Features from './pages/public/Features';
import { AuthProvider } from './contexts/AuthContext';
import { PublicLandingLocaleProvider } from './contexts/PublicLandingLocaleContext';
import AppEntry from './pages/AppEntry';
import { OBSOLETE_OPERATOR_PATHS } from './constants/publicSite';
import { isMarketingPublicHost, isPlatformPortalHost } from './pages/portalHost';
import OwnerPortalShell from './pages/owner/OwnerPortalShell';
import OwnerOverview from './pages/owner/OwnerOverview';
import OwnerUsers from './pages/owner/OwnerUsers';
import OwnerCatalog from './pages/owner/OwnerCatalog';
import OwnerEconomy from './pages/owner/OwnerEconomy';
import OwnerCosts from './pages/owner/OwnerCosts';
import OwnerMessages from './pages/owner/OwnerMessages';

/**
 * Operator SPA shell removed after FINAL_WEB_TO_MOBILE_PARITY_MATRIX.csv.
 * Day-to-day ops live in Expo (mobile/linas-ai). Web keeps marketing + thin auth.
 */

function PublicMarketingShell() {
  if (isPlatformPortalHost()) return <Navigate to="/login" replace />;
  return (
    <PublicLandingLocaleProvider>
      <Outlet />
    </PublicLandingLocaleProvider>
  );
}

function LoginRoute() {
  if (isMarketingPublicHost()) return <Navigate to="/#get-app" replace />;
  return <Login />;
}

function OwnerGate() {
  if (isMarketingPublicHost()) return <Navigate to="/#get-app" replace />;
  return <OwnerPortalShell />;
}

function App() {
  return (
    <Router>
      <AuthProvider>
        <Toaster position="top-right" />
        <Routes>
          <Route element={<PublicMarketingShell />}>
            <Route path="/" element={<Landing />} />
            {/* Public web is marketing-only — no Create Account. */}
            <Route path="/register" element={<Navigate to="/#get-app" replace />} />
            <Route path="/about" element={<About />} />
            <Route path="/contact" element={<Contact />} />
            <Route path="/pricing" element={<Pricing />} />
            <Route path="/features" element={<Features />} />
          </Route>
          {/* Mobile forgot/reset/verify stay on marketing. Web login is portal-only. */}
          <Route path="/login" element={<LoginRoute />} />
          <Route path="/forgot-password" element={<ForgotPassword />} />
          <Route path="/reset-password" element={<ResetPassword />} />
          <Route path="/verify-email" element={<VerifyEmail />} />

          <Route path="/app" element={<AppEntry />} />
          <Route path="/owner" element={<OwnerGate />}>
            <Route index element={<OwnerOverview />} />
            <Route path="users" element={<OwnerUsers />} />
            <Route path="messages" element={<OwnerMessages />} />
            <Route path="catalog" element={<OwnerCatalog />} />
            <Route path="economy" element={<OwnerEconomy />} />
            <Route path="costs" element={<OwnerCosts />} />
          </Route>
          {OBSOLETE_OPERATOR_PATHS.map((path) => (
            <Route key={path} path={path} element={<Navigate to="/#get-app" replace />} />
          ))}
          <Route path="/*" element={<AppEntry />} />
        </Routes>
      </AuthProvider>
    </Router>
  );
}

export default App;
