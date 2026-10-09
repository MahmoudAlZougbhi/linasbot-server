// @ts-nocheck
import { useState } from 'react';
import { NavLink, Navigate, Outlet, useLocation } from 'react-router-dom';
import {
  ArrowRightOnRectangleIcon,
  BanknotesIcon,
  BeakerIcon,
  BookOpenIcon,
  BuildingStorefrontIcon,
  ChatBubbleLeftRightIcon,
  ChatBubbleOvalLeftEllipsisIcon,
  ClipboardDocumentListIcon,
  HomeIcon,
  QuestionMarkCircleIcon,
  SignalIcon,
  TagIcon,
  Bars3Icon,
  XMarkIcon,
} from '@heroicons/react/24/outline';
import { useAuth } from '../../contexts/AuthContext';

const legacyOwnerLinks = [
  { to: '/owner', label: 'Overview' },
  { to: '/owner/users', label: 'Users' },
  { to: '/owner/tenants', label: 'Tenants' },
  { to: '/owner/messages', label: 'Message flow' },
  { to: '/owner/traces', label: 'Traces' },
  { to: '/owner/copilot', label: 'Copilot chats' },
  { to: '/owner/knowledge', label: 'Knowledge' },
  { to: '/owner/qa', label: 'Q&A' },
  { to: '/owner/catalog', label: 'Message catalog' },
  { to: '/owner/economy', label: 'Message economy' },
  { to: '/owner/costs', label: 'Costs' },
  { to: '/owner/brains', label: 'Brains' },
  { to: '/owner/audit', label: 'Audit' },
  { to: '/owner/health', label: 'Health' },
];
void legacyOwnerLinks;

const groups = [
  { title: 'Business', items: [
    { href: '/owner', label: 'Overview', icon: HomeIcon, end: true },
    { href: '/owner/tenants', label: 'Businesses', icon: BuildingStorefrontIcon },
  ] },
  { title: 'Messages', items: [
    { href: '/owner/messages', label: 'Customer messages', icon: ChatBubbleLeftRightIcon },
    { href: '/owner/copilot', label: 'Copilot chats', icon: ChatBubbleOvalLeftEllipsisIcon },
  ] },
  { title: 'AI knowledge', items: [
    { href: '/owner/knowledge', label: 'Copilot knowledge', icon: BookOpenIcon },
    { href: '/owner/qa', label: 'Copilot answers', icon: QuestionMarkCircleIcon },
    { href: '/owner/brains', label: 'Test the AI', icon: BeakerIcon },
  ] },
  { title: 'Plans & billing', items: [
    { href: '/owner/catalog', label: 'Plans & prices', icon: TagIcon, also: ['/owner/economy', '/owner/copilot-pricing'] },
    { href: '/owner/copilot-pricing', label: 'Copilot pricing', icon: BanknotesIcon },
    { href: '/owner/costs', label: 'AI costs', icon: BanknotesIcon },
  ] },
  { title: 'System', items: [
    { href: '/owner/audit', label: 'Activity log', icon: ClipboardDocumentListIcon },
    { href: '/owner/health', label: 'System status', icon: SignalIcon },
  ] },
];

export default function OwnerPortalShell() {
  const { user, loading, logout } = useAuth();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [advanced, setAdvanced] = useState(false);
  if (loading) return <div className="grid min-h-screen place-items-center font-owner text-slate-700">Loading…</div>;
  if (!user) return <Navigate to="/login" replace />;
  if (user.role !== 'platform_owner') return <Navigate to="/app" replace />;

  const nav = (
    <nav aria-label="Owner portal" className="flex-1 space-y-5 overflow-y-auto px-3 py-4">
      {groups.map((group) => (
        <div key={group.title}>
          <p className="px-3 text-xs font-semibold uppercase tracking-[0.08em] text-slate-400">{group.title}</p>
          <div className="mt-2 space-y-1">
            {group.items.map((item) => {
              const active = location.pathname === item.href || (item.also || []).includes(location.pathname) || (item.end && location.pathname === '/owner');
              return (
                <NavLink
                  key={item.href}
                  to={item.href}
                  end={Boolean(item.end)}
                  aria-current={active ? 'page' : undefined}
                  onClick={() => setOpen(false)}
                  className={`flex h-10 items-center gap-2 rounded-lg px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2DD4BF] focus-visible:ring-offset-2 focus-visible:ring-offset-slate-900 ${active ? 'bg-[#134E4A] text-white' : 'text-slate-300 hover:bg-white/5'}`}
                  style={active ? { boxShadow: 'inset 3px 0 0 #2DD4BF' } : undefined}
                >
                  <item.icon className="h-5 w-5" />
                  {item.label}
                </NavLink>
              );
            })}
          </div>
        </div>
      ))}
      <div>
        <button type="button" className="px-3 text-xs font-semibold uppercase tracking-[0.08em] text-slate-400" aria-expanded={advanced} onClick={() => setAdvanced((value) => !value)}>Advanced</button>
        {advanced ? (
          <div className="mt-2">
            <NavLink to="/owner/traces" onClick={() => setOpen(false)} aria-current={location.pathname.startsWith('/owner/traces') ? 'page' : undefined} className={`flex h-10 items-center gap-2 rounded-lg px-3 text-sm ${location.pathname.startsWith('/owner/traces') ? 'bg-[#134E4A] text-white' : 'text-slate-300 hover:bg-white/5'}`}>
              <ClipboardDocumentListIcon className="h-5 w-5" /> AI traces
            </NavLink>
          </div>
        ) : null}
      </div>
    </nav>
  );

  return (
    <div className="owner-scroll min-h-screen bg-slate-50 font-owner text-slate-900 md:flex">
      <aside className="sticky top-0 hidden h-screen w-[248px] flex-col bg-slate-900 md:flex">
        <div className="px-5 pt-5">
          <p className="text-base font-semibold text-white">Linas AI</p>
          <p className="text-sm text-slate-300">Owner Portal</p>
        </div>
        {nav}
        <div className="border-t border-white/10 p-4">
          <p className="truncate text-sm text-slate-300" title={user.email}>{user.email}</p>
          <button type="button" onClick={logout} className="mt-2 inline-flex items-center gap-2 text-sm text-[#5EEAD4]">
            <ArrowRightOnRectangleIcon className="h-4 w-4" /> Sign out
          </button>
        </div>
      </aside>
      {open ? (
        <div className="fixed inset-0 z-40 md:hidden">
          <button type="button" aria-label="Close menu" className="absolute inset-0 bg-slate-900/50" onClick={() => setOpen(false)} />
          <aside className="relative flex h-full w-[248px] flex-col bg-slate-900">{nav}</aside>
        </div>
      ) : null}
      <div className="min-w-0 flex-1">
        <header className="sticky top-0 z-20 border-b border-slate-200 bg-white">
          <div className="mx-auto flex h-16 max-w-[1280px] items-center gap-3 px-6 lg:px-8">
            <button type="button" className="grid h-11 w-11 place-items-center lg:hidden" aria-label="Open menu" onClick={() => setOpen(true)}>
              {open ? <XMarkIcon className="h-5 w-5" /> : <Bars3Icon className="h-5 w-5" />}
            </button>
            <div id="owner-page-header" className="min-w-0 flex-1" />
          </div>
        </header>
        <main className="mx-auto min-w-0 max-w-[1280px] overflow-x-clip px-6 py-6 lg:px-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
