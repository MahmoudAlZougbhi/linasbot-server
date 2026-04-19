import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Toaster } from 'react-hot-toast';

// Components
import Sidebar from './components/Layout/Sidebar';
import Header from './components/Layout/Header';
import LoadingScreen from './components/Common/LoadingScreen';
import ProtectedRoute from './components/Auth/ProtectedRoute';

// Pages
import Dashboard from './pages/Dashboard';
import Testing from './pages/Testing';
import SimpleApiTest from './pages/SimpleApiTest';
import Training from './pages/Training';
import ContentManagers from './pages/ContentManagers';
import ActivityFlow from './pages/ActivityFlow';
import LiveChat from './pages/LiveChat';
import MobileLiveChat from './pages/MobileLiveChat';
import SmartMessaging from './pages/SmartMessaging';
import Analytics from './pages/Analytics';
import Settings from './pages/Settings';
import Login from './pages/Login';
import Register from './pages/Register';

// Contexts
import { AuthProvider } from './contexts/AuthContext';
import { PermissionsProvider } from './contexts/PermissionsContext';
import { OperatorStatusProvider } from './contexts/OperatorStatusContext';

// Hooks
import { useApi } from './hooks/useApi';

function AppContent() {
  const [loading, setLoading] = useState(true);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const { botStatus, fetchBotStatus } = useApi();

  useEffect(() => {
    // TEST: fetchBotStatus temporarily disabled to check if it causes login hang
    // try {
    //   await fetchBotStatus();
    // } catch (error) {
    //   // silent
    // }
    setTimeout(() => setLoading(false), 300);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  if (loading) {
    return <LoadingScreen />;
  }

  return (
      <OperatorStatusProvider>
      <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-100">
        {/* Background Effects */}
        <div className="fixed inset-0 overflow-hidden pointer-events-none">
          <div className="absolute -top-40 -right-40 w-80 h-80 bg-primary-200 rounded-full mix-blend-multiply filter blur-xl opacity-70 animate-pulse-slow"></div>
          <div className="absolute -bottom-40 -left-40 w-80 h-80 bg-secondary-200 rounded-full mix-blend-multiply filter blur-xl opacity-70 animate-pulse-slow animation-delay-400"></div>
          <div className="absolute top-40 left-1/2 w-80 h-80 bg-accent-200 rounded-full mix-blend-multiply filter blur-xl opacity-70 animate-pulse-slow animation-delay-800"></div>
        </div>

        <div className="relative flex h-screen overflow-hidden">
          {/* Sidebar - collapsible */}
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

          {/* Main Content */}
          <div className="flex-1 flex flex-col overflow-hidden">
            {/* Header */}
            <Header
              onMenuClick={() => setSidebarCollapsed(!sidebarCollapsed)}
              botStatus={botStatus}
            />

            {/* Page Content - full width when sidebar collapsed */}
            <main className="flex-1 overflow-y-auto p-6">
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.15 }}
                className={sidebarCollapsed ? "max-w-full" : "max-w-7xl mx-auto"}
              >
                <Routes>
                  {/* TEST: Inner ProtectedRoute removed - protection only at top level */}
                  <Route path="/" element={<Dashboard />} />
                  <Route path="/testing" element={<Testing />} />
                  <Route path="/api-debug" element={<SimpleApiTest />} />
                  <Route path="/training" element={<Training />} />
                  <Route path="/content-managers" element={<ContentManagers />} />
                  <Route path="/activity-flow" element={<ActivityFlow />} />
                  <Route path="/live-chat" element={<LiveChat />} />
                  <Route path="/analytics" element={<Analytics />} />
                  <Route path="/smart-messaging" element={<SmartMessaging />} />
                  <Route path="/settings" element={<Settings />} />

                  {/* Catch all - redirect to dashboard */}
                  <Route path="*" element={<Navigate to="/" replace />} />
                </Routes>
              </motion.div>
            </main>
          </div>
        </div>

        {/* Toast Notifications */}
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
        <MobileLiveChat />
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
            {/* Public Routes */}
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />

            <Route
              path="/mobile/live-chat"
              element={
                <ProtectedRoute>
                  <MobileLiveChatRoute />
                </ProtectedRoute>
              }
            />

            {/* Protected App Routes */}
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
