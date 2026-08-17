import { NavLink, Navigate, Outlet } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';

const links = [
  { to: '/owner', label: 'Overview' },
  { to: '/owner/users', label: 'Users' },
  { to: '/owner/copilot-setup', label: 'Owner Copilot Setup' },
];

export default function OwnerPortalShell() {
  const { user, loading, logout } = useAuth();
  if (loading) return <div className="min-h-screen grid place-items-center">Loading…</div>;
  if (!user) return <Navigate to="/login" replace />;
  if (user.role !== 'platform_owner') return <Navigate to="/app" replace />;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 md:flex">
      <aside className="border-b border-slate-800 bg-slate-900 p-5 md:min-h-screen md:w-64 md:border-b-0 md:border-r">
        <div className="mb-7">
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-teal-400">Linas.ai</p>
          <h1 className="mt-1 text-xl font-semibold">Owner Portal</h1>
          <p className="mt-2 truncate text-xs text-slate-400">{user.email}</p>
        </div>
        <nav className="flex gap-2 overflow-x-auto md:flex-col">
          {links.map(({ to, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/owner'}
              className={({ isActive }) =>
                `whitespace-nowrap rounded-lg px-3 py-2 text-sm ${
                  isActive ? 'bg-teal-500 text-slate-950' : 'text-slate-300 hover:bg-slate-800'
                }`
              }
            >
              {label}
            </NavLink>
          ))}
        </nav>
        <button type="button" onClick={logout} className="mt-7 text-sm text-slate-400 hover:text-white">
          Sign out
        </button>
      </aside>
      <main className="min-w-0 flex-1 p-5 md:p-8">
        <Outlet />
      </main>
    </div>
  );
}
