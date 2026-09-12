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
import OwnerPortalShell from './pages/owner/OwnerPortalShell';
import OwnerOverview from './pages/owner/OwnerOverview';
import OwnerUsers from './pages/owner/OwnerUsers';
import OwnerCopilotSetup from './pages/owner/OwnerCopilotSetup';
import OwnerCatalog from './pages/owner/OwnerCatalog';
import OwnerCosts from './pages/owner/OwnerCosts';
import OwnerLab from './pages/owner/OwnerLab';
import OwnerMessages from './pages/owner/OwnerMessages';

/**
 * Operator SPA shell removed after FINAL_WEB_TO_MOBILE_PARITY_MATRIX.csv.
 * Day-to-day ops live in Expo (mobile/linas-ai). Web keeps marketing + thin auth.
 */

function PublicMarketingShell() {
  return (
    <PublicLandingLocaleProvider>
      <Outlet />
    </PublicLandingLocaleProvider>
  );
}

function App() {
  return (
    <Router>
      <AuthProvider>
        <Toaster position="top-right" />
        <Routes>
          <Route element={<PublicMarketingShell />}>
            <Route path="/" element={<Landing />} />
            {/* Public web is marketing-only — no Create Account. Ops login stays at /login. */}
            <Route path="/register" element={<Navigate to="/#get-app" replace />} />
            <Route path="/about" element={<About />} />
            <Route path="/contact" element={<Contact />} />
            <Route path="/pricing" element={<Pricing />} />
            <Route path="/features" element={<Features />} />
          </Route>
          {/* Thin auth — not linked from marketing CTAs; mobile forgot-password opens these. */}
          <Route path="/login" element={<Login />} />
          <Route path="/forgot-password" element={<ForgotPassword />} />
          <Route path="/reset-password" element={<ResetPassword />} />
          <Route path="/verify-email" element={<VerifyEmail />} />

          {/* Former operator SPA routes → mobile app CTA (parity matrix committed first). */}
          <Route path="/mobile/live-chat" element={<Navigate to="/#get-app" replace />} />
          <Route path="/app" element={<AppEntry />} />
          <Route path="/owner" element={<OwnerPortalShell />}>
            <Route index element={<OwnerOverview />} />
            <Route path="users" element={<OwnerUsers />} />
            <Route path="messages" element={<OwnerMessages />} />
            <Route path="copilot-setup" element={<OwnerCopilotSetup />} />
            <Route path="catalog" element={<OwnerCatalog />} />
            <Route path="costs" element={<OwnerCosts />} />
            <Route path="lab" element={<OwnerLab />} />
          </Route>
          <Route path="/training" element={<Navigate to="/#get-app" replace />} />
          <Route path="/content-managers/*" element={<Navigate to="/#get-app" replace />} />
          <Route path="/activity-flow" element={<Navigate to="/#get-app" replace />} />
          <Route path="/live-chat" element={<Navigate to="/#get-app" replace />} />
          <Route path="/analytics" element={<Navigate to="/#get-app" replace />} />
          <Route path="/smart-messaging" element={<Navigate to="/#get-app" replace />} />
          <Route path="/social-posts" element={<Navigate to="/#get-app" replace />} />
          <Route path="/wallet" element={<Navigate to="/#get-app" replace />} />
          <Route path="/settings" element={<Navigate to="/#get-app" replace />} />
          <Route path="/testing" element={<Navigate to="/#get-app" replace />} />
          <Route path="/api-debug" element={<Navigate to="/#get-app" replace />} />
          <Route path="/*" element={<AppEntry />} />
        </Routes>
      </AuthProvider>
    </Router>
  );
}

export default App;
