import { useState, useEffect, Suspense, lazy } from "react";
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Toaster } from 'react-hot-toast';

import Sidebar from './components/Layout/Sidebar';
import Header from './components/Layout/Header';
import LoadingScreen from './components/Common/LoadingScreen';
import ProtectedRoute from './components/Auth/ProtectedRoute';
import Login from './pages/Login';
import ForgotPassword from './pages/ForgotPassword';
import ResetPassword from './pages/ResetPassword';
import VerifyEmail from './pages/VerifyEmail';
import Landing from './pages/public/Landing';
import Register from './pages/public/Register';
import About from './pages/public/About';
import Contact from './pages/public/Contact';
import NotFound from './pages/NotFound';
import { AuthProvider } from './contexts/AuthContext';
import { PermissionsProvider } from './contexts/PermissionsContext';
import { OperatorStatusProvider } from './contexts/OperatorStatusContext';
import { useApi } from './hooks/useApi';

const Dashboard = lazy(() => import('./pages/Dashboard'));
const Testing = lazy(() => import('./pages/Testing'));
const SimpleApiTest = lazy(() => import('./pages/SimpleApiTest'));
const Training = lazy(() => import('./pages/Training'));
const ContentManagers = lazy(() => import('./pages/ContentManagers'));
const CmSectionPage = lazy(() => import('./pages/content-managers/CmSectionPage'));
const CmPricesPage = lazy(() => import('./pages/content-managers/CmPricesPage'));
const CmFaqPage = lazy(() => import('./pages/content-managers/CmFaqPage'));
const CmLearningInboxPage = lazy(() => import('./pages/content-managers/CmLearningInboxPage'));
const CmPublishPage = lazy(() => import('./pages/content-managers/CmPublishPage'));
const CmAiBasicsPage = lazy(() => import('./pages/content-managers/CmAiBasicsPage'));
const CmLanguagesPage = lazy(() => import('./pages/content-managers/CmLanguagesPage'));
const CmStylePage = lazy(() => import('./pages/content-managers/CmStylePage'));
const CmDynamicMessagesPage = lazy(() => import('./pages/content-managers/CmDynamicMessagesPage'));
const CmServicesPage = lazy(() => import('./pages/content-managers/CmServicesPage'));
const CmBranchesPage = lazy(() => import('./pages/content-managers/CmBranchesPage'));
const CmKnowledgePage = lazy(() => import('./pages/content-managers/CmKnowledgePage'));
const CmCarePage = lazy(() => import('./pages/content-managers/CmCarePage'));
const CmHandoffPage = lazy(() => import('./pages/content-managers/CmHandoffPage'));
const CmRestrictedPage = lazy(() => import('./pages/content-managers/CmRestrictedPage'));
const CmSourcesPage = lazy(() => import('./pages/content-managers/CmSourcesPage'));
const ActivityFlow = lazy(() => import('./pages/ActivityFlow'));
const LiveChat = lazy(() => import('./pages/LiveChat'));
const MobileLiveChat = lazy(() => import('./pages/MobileLiveChat'));
const SmartMessaging = lazy(() => import('./pages/SmartMessaging'));
const Settings = lazy(() => import('./pages/Settings'));
const Wallet = lazy(() => import('./pages/Wallet'));

const RouteFallback = () => (
  <div className="flex items-center justify-center py-24 text-slate-600 text-sm">
    Loading…
  </div>
);

function AppContent() {
  const [loading, setLoading] = useState(true);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const { botStatus } = useApi();

  useEffect(() => {
    setTimeout(() => setLoading(false), 300);
  }, []);

  if (loading) {
    return <LoadingScreen />;
  }

  return (
      <OperatorStatusProvider>
      <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-100">
        <div className="fixed inset-0 overflow-hidden pointer-events-none">
          <div className="absolute -top-40 -right-40 w-80 h-80 bg-primary-200 rounded-full mix-blend-multiply filter blur-xl opacity-70 animate-pulse-slow"></div>
          <div className="absolute -bottom-40 -left-40 w-80 h-80 bg-secondary-200 rounded-full mix-blend-multiply filter blur-xl opacity-70 animate-pulse-slow animation-delay-400"></div>
          <div className="absolute top-40 left-1/2 w-80 h-80 bg-accent-200 rounded-full mix-blend-multiply filter blur-xl opacity-70 animate-pulse-slow animation-delay-800"></div>
        </div>

        <div className="relative flex h-screen overflow-hidden">
          <motion.div
            initial={false}
            animate={{ width: sidebarCollapsed ? 80 : 320 }}
            transition={{ duration: 0.25, ease: 'easeInOut' }}
            className="relative z-30 flex-shrink-0 overflow-hidden"
          >
            <Sidebar
              collapsed={sidebarCollapsed}
              onToggleCollapse={() => setSidebarCollapsed(!sidebarCollapsed)}
              onClose={() => setSidebarCollapsed(true)}
            />
          </motion.div>

          <div className="flex-1 flex flex-col overflow-hidden">
            <Header
              onMenuClick={() => setSidebarCollapsed(!sidebarCollapsed)}
              botStatus={botStatus}
            />

            <main className="flex-1 overflow-y-auto p-6">
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.15 }}
                className={sidebarCollapsed ? "max-w-full" : "max-w-7xl mx-auto"}
              >
                <Suspense fallback={<RouteFallback />}>
                  <Routes>
                    <Route path="/app" element={<Dashboard />} />
                    <Route path="/testing" element={<Testing />} />
                    <Route path="/api-debug" element={<SimpleApiTest />} />
                    <Route path="/training" element={<Training />} />
                    <Route path="/content-managers" element={<ContentManagers />} />
                    <Route path="/content-managers/publish" element={<CmPublishPage />} />
                    <Route path="/content-managers/prices" element={<CmPricesPage />} />
                    <Route path="/content-managers/faq" element={<CmFaqPage />} />
                    <Route path="/content-managers/learning-inbox" element={<CmLearningInboxPage />} />
                    <Route path="/content-managers/ai-basics" element={<CmAiBasicsPage />} />
                    <Route path="/content-managers/languages" element={<CmLanguagesPage />} />
                    <Route path="/content-managers/style" element={<CmStylePage />} />
                    <Route path="/content-managers/dynamic-messages" element={<CmDynamicMessagesPage />} />
                    <Route path="/content-managers/services" element={<CmServicesPage />} />
                    <Route path="/content-managers/branches" element={<CmBranchesPage />} />
                    <Route path="/content-managers/knowledge" element={<CmKnowledgePage />} />
                    <Route path="/content-managers/care" element={<CmCarePage />} />
                    <Route path="/content-managers/handoff" element={<CmHandoffPage />} />
                    <Route path="/content-managers/restricted" element={<CmRestrictedPage />} />
                    <Route path="/content-managers/sources" element={<CmSourcesPage />} />
                    <Route path="/content-managers/:sectionSlug" element={<CmSectionPage />} />
                    <Route path="/activity-flow" element={<ActivityFlow />} />
                    <Route path="/live-chat" element={<LiveChat />} />
                    <Route path="/analytics" element={<Navigate to="/app" replace />} />
                    <Route path="/smart-messaging" element={<SmartMessaging />} />
                    <Route path="/wallet" element={<Wallet />} />
                    <Route path="/settings" element={<Settings />} />
                    <Route path="*" element={<NotFound />} />
                  </Routes>
                </Suspense>
              </motion.div>
            </main>
          </div>
        </div>

        <Toaster
          position="top-right"
          toastOptions={{
            duration: 4000,
            style: {
              background: 'rgba(255, 255, 255, 0.9)',
              backdropFilter: 'blur(10px)',
              border: '1px solid rgba(255, 255, 255, 0.2)',
              borderRadius: '12px',
              color: '#334155',
              fontWeight: '500',
            },
            success: {
              iconTheme: {
                primary: '#10b981',
                secondary: '#ffffff',
              },
            },
            error: {
              iconTheme: {
                primary: '#ef4444',
                secondary: '#ffffff',
              },
            },
          }}
        />
      </div>
      </OperatorStatusProvider>
  );
}

function MobileLiveChatRoute() {
  return (
    <OperatorStatusProvider>
      <div className="h-[100dvh] overflow-hidden bg-slate-950">
        <Suspense fallback={<RouteFallback />}>
          <MobileLiveChat />
        </Suspense>
      </div>
    </OperatorStatusProvider>
  );
}

function App() {
  return (
    <Router>
      <AuthProvider>
        <PermissionsProvider>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/register" element={<Register />} />
            <Route path="/about" element={<About />} />
            <Route path="/contact" element={<Contact />} />
            <Route path="/login" element={<Login />} />
            <Route path="/forgot-password" element={<ForgotPassword />} />
            <Route path="/reset-password" element={<ResetPassword />} />
            <Route path="/verify-email" element={<VerifyEmail />} />

            <Route
              path="/mobile/live-chat"
              element={
                <ProtectedRoute>
                  <MobileLiveChatRoute />
                </ProtectedRoute>
              }
            />

            <Route path="/*" element={
              <ProtectedRoute>
                <AppContent />
              </ProtectedRoute>
            } />
          </Routes>
        </PermissionsProvider>
      </AuthProvider>
    </Router>
  );
}

export default App;
