import { useEffect, useState } from 'react';
import { ownerApi } from './ownerApi';

/** @param {{ tenantId: string; onClose: () => void }} props */
function LogsPanel({ tenantId, onClose }) {
  const [logs, setLogs] = useState(/** @type {OwnerInteractionLog[]} */ ([]));
  const [error, setError] = useState('');
  useEffect(() => {
    ownerApi.logs(tenantId).then((data) => setLogs(data.data || [])).catch((reason) => setError(reason.message));
  }, [tenantId]);
  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-black/75 p-4">
      <div className="mx-auto max-w-5xl rounded-xl bg-slate-900 p-5">
        <div className="flex justify-between gap-4">
          <div>
            <h3 className="text-lg font-semibold">Interaction Logs</h3>
            <p className="text-sm text-slate-400">Tenant: {tenantId} · exact tenant scope</p>
          </div>
          <button type="button" onClick={onClose} className="text-slate-400 hover:text-white">Close</button>
        </div>
        {error && <p className="mt-4 text-red-300">{error}</p>}
        <div className="mt-5 space-y-3">
          {logs.length === 0 && !error && <p className="text-slate-400">No tenant-tagged logs found.</p>}
          {logs.slice().reverse().map((log, index) => (
            <article key={`${log.timestamp}-${log.message_id || index}`} className="rounded-lg bg-slate-950 p-4 text-sm">
              <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-400">
                <span>{log.timestamp}</span><span>{log.channel}</span><span>{log.source}</span>
                {log.faq_match?.faq_id && <span>FAQ: {log.faq_match.faq_id}</span>}
              </div>
              <p className="mt-3"><span className="text-teal-400">Customer:</span> {log.user_message || '—'}</p>
              <p className="mt-2"><span className="text-violet-400">AI:</span> {log.bot_to_user || '—'}</p>
            </article>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function OwnerUsers() {
  const [subscribers, setSubscribers] = useState(/** @type {OwnerSubscriber[]} */ ([]));
  const [logsTenant, setLogsTenant] = useState('');
  const [error, setError] = useState('');

  const load = () => ownerApi.subscribers()
    .then((data) => setSubscribers(data.subscribers || []))
    .catch((reason) => setError(reason.message));
  useEffect(() => {
    let live = true;
    ownerApi.subscribers()
      .then((data) => live && setSubscribers(data.subscribers || []))
      .catch((reason) => live && setError(reason.message));
    return () => { live = false; };
  }, []);

  /** @param {DashboardUser} user @param {Record<string, unknown>} changes */
  const update = async (user, changes) => {
    try {
      await ownerApi.updateUser(user.id, changes);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Update failed');
    }
  };
  /** @param {DashboardUser} user */
  const resetPassword = (user) => {
    const password = window.prompt(`Temporary password for ${user.email} (12+ characters)`);
    if (password) update(user, { password });
  };

  return (
    <div className="space-y-6">
      <header>
        <h2 className="text-2xl font-semibold">Users & subscribers</h2>
        <p className="mt-1 text-sm text-slate-400">Billing is batched; Interaction Logs open only for the selected tenant.</p>
      </header>
      {error && <p role="alert" className="rounded-lg bg-red-950 p-3 text-red-200">{error}</p>}
      <div className="overflow-x-auto rounded-xl border border-slate-800">
        <table className="min-w-full divide-y divide-slate-800 text-left text-sm">
          <thead className="bg-slate-900 text-slate-400">
            <tr>{['Subscriber', 'Plan', 'Seats / roles', 'Credits', 'Actions'].map((label) => <th key={label} className="px-4 py-3">{label}</th>)}</tr>
          </thead>
          <tbody className="divide-y divide-slate-800 bg-slate-950">
            {subscribers.map((subscriber) => (
              <tr key={subscriber.tenant_id}>
                <td className="px-4 py-4">
                  <p>{subscriber.email || 'No email'}</p>
                  <p className="text-xs text-slate-500">{subscriber.business_name || subscriber.tenant_id}</p>
                  <span className={`mt-1 inline-block text-xs ${subscriber.status === 'blocked' ? 'text-red-400' : 'text-emerald-400'}`}>{subscriber.status}</span>
                </td>
                <td className="px-4 py-4"><p>{subscriber.subscription}</p><p className="text-xs text-slate-500">{subscriber.membership}</p></td>
                <td className="px-4 py-4"><p>{subscriber.seats_created}</p><p className="text-xs text-slate-500">{subscriber.roles.join(', ')}</p></td>
                <td className="px-4 py-4"><p>{subscriber.credits_used} used</p><p className="text-xs text-slate-500">{subscriber.credits_remaining} remaining</p></td>
                <td className="px-4 py-4">
                  <div className="flex flex-wrap gap-2">
                    <button type="button" onClick={() => setLogsTenant(subscriber.tenant_id)} className="rounded bg-teal-500 px-2 py-1 text-slate-950">Interaction Logs</button>
                    {subscriber.users.filter((user) => user.role !== 'platform_owner').map((user) => (
                      <span key={user.id} className="flex gap-1">
                        <select
                          aria-label={`Role for ${user.email}`}
                          value={String(user.role || 'viewer')}
                          onChange={(event) => update(user, { role: event.target.value })}
                          className="rounded border border-slate-700 bg-slate-900 px-2 py-1"
                        >
                          <option value="admin">Admin</option>
                          <option value="operator">Operator</option>
                          <option value="viewer">Viewer</option>
                        </select>
                        <button type="button" onClick={() => resetPassword(user)} className="rounded bg-slate-800 px-2 py-1">Password</button>
                        <button
                          type="button"
                          onClick={() => update(user, { status: user.status === 'blocked' ? 'active' : 'blocked' })}
                          className="rounded bg-slate-800 px-2 py-1"
                        >
                          {user.status === 'blocked' ? 'Unblock' : 'Block'}
                        </button>
                      </span>
                    ))}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {logsTenant && <LogsPanel tenantId={logsTenant} onClose={() => setLogsTenant('')} />}
    </div>
  );
}
