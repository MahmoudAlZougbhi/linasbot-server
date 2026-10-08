// @ts-nocheck
import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ownerApi } from './ownerApi';
import { useLoad } from './lib/useLoad';
import { label } from './lib/labels';
import { formatDateTime } from './lib/format';
import { replyHtml } from './replyFormat';
import PageHeader from './ui/PageHeader';
import DataTable from './ui/DataTable';
import Badge from './ui/Badge';
import Button from './ui/Button';
import ConfirmDialog from './ui/ConfirmDialog';
import Alert from './ui/Alert';
import TechDetails from './ui/TechDetails';
import { statusLabel, statusTone } from './lib/status';

function mergeSubscribers(current, incoming) {
  const byTenant = new Map(current.map((row) => [row.tenant_id, row]));
  incoming.forEach((row) => {
    const existing = byTenant.get(row.tenant_id);
    if (!existing) byTenant.set(row.tenant_id, row);
    else byTenant.set(row.tenant_id, { ...existing, users: [...existing.users, ...row.users.filter((user) => !existing.users.some((item) => item.id === user.id))] });
  });
  return [...byTenant.values()];
}

export default function OwnerUsers() {
  const [extra, setExtra] = useState(/** @type {any[]} */ ([]));
  const [cursor, setCursor] = useState('');
  const [showTest, setShowTest] = useState(false);
  const [logs, setLogs] = useState(/** @type {any} */ (null));
  const [confirm, setConfirm] = useState(/** @type {any} */ (null));
  const [roleUser, setRoleUser] = useState(/** @type {any} */ (null));
  const [passwordUser, setPasswordUser] = useState(/** @type {any} */ (null));
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const state = useLoad(() => ownerApi.subscribers().then((data) => { setCursor(data.next_cursor || ''); return data.subscribers || []; }), []);
  const rows = useMemo(() => {
    const source = mergeSubscribers(state.data || [], extra);
    return source.flatMap((business) => (business.users || []).map((user) => ({ ...user, business })))
      .filter((user) => showTest || !user.business.hide_by_default);
  }, [state.data, extra, showTest]);

  const chat = useLoad(() => (logs ? ownerApi.logs(logs.tenant_id).then((data) => data.data || []) : Promise.resolve(null)), [logs?.tenant_id]);

  return (
    <div className="space-y-6">
      <PageHeader title="Users" subtitle="People who can sign in, and what they're allowed to do." />
      {state.status === 'error' ? <Alert title="We couldn't load users." detail={state.error} /> : null}
      <label className="flex items-center gap-2 text-sm text-slate-700"><input type="checkbox" checked={showTest} onChange={(event) => setShowTest(event.target.checked)} /> Show test accounts</label>
      <DataTable
        loading={state.status === 'loading'}
        columns={[
          { key: 'email', label: 'User', render: (row) => <span className="font-medium text-slate-900">{row.email}</span> },
          { key: 'business', label: 'Business', render: (row) => <Link className="text-[#0F766E]" to={`/owner/tenants?open=${row.business.tenant_id}`}>{row.business.business_name || row.business.tenant_id}</Link> },
          { key: 'role', label: 'Role', render: (row) => label('role', row.role) },
          { key: 'status', label: 'Status', render: (row) => <Badge tone={statusTone('user', row.business.hide_by_default && row.status !== 'blocked' ? 'test' : row.status)}>{statusLabel('user', row.business.hide_by_default && row.status !== 'blocked' ? 'test' : row.status)}</Badge> },
          { key: 'menu', label: '', render: (row) => (
            <Button variant="tertiary" onClick={() => setLogs(row.business)}>Chat history</Button>
          ) },
        ]}
        rows={rows}
        getRowId={(row) => row.id}
        searchPlaceholder="Search by email or business"
        searchText={(row) => `${row.email} ${row.business.business_name || ''}`}
        empty={<p className="p-6 text-sm text-slate-600">No users match.</p>}
      />
      {cursor ? <Button variant="secondary" onClick={() => { void ownerApi.subscribers(cursor).then((data) => { setExtra((current) => mergeSubscribers(current, data.subscribers || [])); setCursor(data.next_cursor || ''); }); }}>Load more users</Button> : null}
      {logs ? (
        <div className="fixed inset-0 z-50 flex justify-end bg-slate-900/40">
          <div className="h-full w-full max-w-[560px] overflow-y-auto bg-white p-5">
            <div className="flex justify-between"><h2 className="text-base font-semibold">Chat history: {logs.business_name || logs.tenant_id}</h2><button type="button" aria-label="Close" onClick={() => setLogs(null)}>Close</button></div>
            <p className="text-sm text-slate-600">Newest first</p>
            {chat.status === 'loading' ? <p className="mt-4 text-sm">Loading…</p> : null}
            {chat.status === 'ready' && (chat.data || []).length === 0 ? <p className="mt-4 text-sm text-slate-600">No chats recorded yet. Chats appear here after this business&apos;s customers message the AI.</p> : null}
            {(chat.data || []).slice().reverse().map((log, index) => (
              <article key={`${log.timestamp}-${index}`} className="mt-4 space-y-2">
                <p className="text-sm text-slate-600">{formatDateTime(log.timestamp)} · {label('channel', log.channel)}</p>
                <p className="rounded-lg bg-slate-100 p-3 text-sm" dir="auto">{log.user_message || '—'}</p>
                <p className="rounded-lg bg-teal-50 p-3 text-sm" dir="auto" dangerouslySetInnerHTML={replyHtml(log.bot_to_user || '')} />
                <TechDetails text={`${log.timestamp} ${log.source || ''}`} />
              </article>
            ))}
          </div>
        </div>
      ) : null}
      {confirm ? <ConfirmDialog title={`Block ${confirm.email}?`} body="They won't be able to sign in until you unblock them. Nothing is deleted." confirmLabel="Block user" onClose={() => setConfirm(null)} onConfirm={async () => { await ownerApi.updateUser(confirm.id, { status: 'blocked' }); setConfirm(null); }} /> : null}
      {roleUser ? (
        <ConfirmDialog title="Change role" body="Choose Admin, Operator, or Viewer, then confirm." confirmLabel="Save role" onClose={() => setRoleUser(null)} onConfirm={async () => { await ownerApi.updateUser(roleUser.id, { role: 'operator' }); setRoleUser(null); }} />
      ) : null}
      {passwordUser ? (
        <div className="fixed inset-0 z-50 grid place-items-center bg-slate-900/40 p-4">
          <form className="w-full max-w-md rounded-xl bg-white p-5" onSubmit={(event) => { event.preventDefault(); if (password.length < 12) { setError('Use at least 12 characters'); return; } void ownerApi.updateUser(passwordUser.id, { password }).then(() => setPasswordUser(null)); }}>
            <h2 className="text-base font-semibold">Reset password</h2>
            <input aria-label="New password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} className="mt-3 h-9 w-full rounded-lg border border-[#7C8798] px-3" />
            {error ? <p className="mt-2 text-sm text-red-800">{error}</p> : null}
            <div className="mt-4 flex justify-end gap-2"><Button variant="secondary" onClick={() => setPasswordUser(null)}>Cancel</Button><Button type="submit">Set password</Button></div>
          </form>
        </div>
      ) : null}
    </div>
  );
}
