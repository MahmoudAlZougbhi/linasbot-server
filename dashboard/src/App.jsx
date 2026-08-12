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
import { PermissionsProvider } from './contexts/PermissionsContext';
import { PublicLandingLocaleProvider } from './contexts/PublicLandingLocaleContext';

/**
 * Operator SPA shell removed after FINAL_WEB_TO_MOBILE_PARITY_MATRIX.csv.
 * Day-to-day ops live in Expo (mobile/linas-ai). Web keeps marketing + thin auth.
 */

/** Minimal stub for bookmarks that still hit former operator paths. */
function UseMobileAppPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 px-6">
      <div className="max-w-md text-center space-y-4">
        <h1 className="text-2xl font-semibold text-slate-900">Use the Linas AI mobile app</h1>
        <p className="text-sm text-slate-600">
          Operator tools (AI Setup, Live Chat, billing, settings) run in the Linas AI app.
          This web surface is marketing and account recovery only.
        </p>
        <a
          href="/#get-app"
          className="inline-flex items-center justify-center rounded-lg bg-teal-700 px-4 py-2 text-sm font-medium text-white hover:bg-teal-800"
        >
          Get the app
        </a>
      </div>
      <Toaster position="top-right" />
    </div>
  );
}

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
        <PermissionsProvider>
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
            <Route path="/app" element={<UseMobileAppPage />} />
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
            <Route path="/*" element={<UseMobileAppPage />} />
          </Routes>
        </PermissionsProvider>
      </AuthProvider>
    </Router>
  );
}

export default App;
