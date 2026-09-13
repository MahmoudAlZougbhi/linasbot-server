import { Navigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { isPlatformPortalHost } from './portalHost';

/**
 * Stub for former operator web paths. Live Chat / AI Setup live in the mobile app.
 * Platform owners never stay here — AppEntry sends them to /owner.
 */
export function UseMobileAppPage() {
  const { user, logout } = useAuth();
  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 px-6">
      <div className="max-w-md text-center space-y-4">
        <h1 className="text-2xl font-semibold text-slate-900">Use the Linas AI mobile app</h1>
        <p className="text-sm text-slate-600">
          Operator tools (AI Setup, Live Chat, billing, settings) run in the Linas AI app.
          This web surface is marketing and account recovery only.
        </p>
        {user ? (
          <p className="text-sm text-slate-500">
            Signed in as {user.email}
          </p>
        ) : null}
        <div className="flex flex-col items-center gap-2">
          <a
            href="/#get-app"
            className="inline-flex items-center justify-center rounded-lg bg-teal-700 px-4 py-2 text-sm font-medium text-white hover:bg-teal-800"
          >
            Get the app
          </a>
          {user ? (
            <button
              type="button"
              onClick={logout}
              className="text-sm text-slate-500 hover:text-slate-800"
            >
              Sign out
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export function PortalOwnerOnlyPage() {
  const { user, logout } = useAuth();
  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-950 px-6 text-slate-100">
      <div className="max-w-md text-center space-y-4">
        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-teal-400">Linas.ai</p>
        <h1 className="text-2xl font-semibold">Platform owner portal</h1>
        <p className="text-sm text-slate-400">
          This host is for the platform owner account only. Workspace accounts use the Linas AI
          mobile app.
        </p>
        {user ? <p className="text-sm text-slate-500">Signed in as {user.email}</p> : null}
        <div className="flex flex-col items-center gap-2">
          <a
            href="/login"
            className="inline-flex items-center justify-center rounded-lg bg-teal-500 px-4 py-2 text-sm font-medium text-slate-950 hover:bg-teal-400"
          >
            Owner sign in
          </a>
          {user ? (
            <button type="button" onClick={logout} className="text-sm text-slate-400 hover:text-white">
              Sign out
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export default function AppEntry() {
  const { user, loading } = useAuth();
  if (loading) return <div className="min-h-screen grid place-items-center">Loading…</div>;
  if (user?.role === 'platform_owner') return <Navigate to="/owner" replace />;
  if (isPlatformPortalHost()) return <PortalOwnerOnlyPage />;
  return <UseMobileAppPage />;
}
