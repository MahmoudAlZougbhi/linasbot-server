import { useEffect, useState } from 'react';
import { ownerApi } from './ownerApi';

export default function OwnerHealth() {
  const [health, setHealth] = useState(/** @type {any} */ (null));
  const [error, setError] = useState('');

  useEffect(() => {
    ownerApi.health().then(setHealth).catch((reason) => setError(reason.message));
  }, []);

  return (
    <div className="space-y-6">
      <header>
        <h2 className="text-2xl font-semibold">Health</h2>
        <p className="mt-1 text-sm text-slate-400">
          Read-only status for the API and the database. QA uses this page. Server logs stay on the hosts:
          journalctl -u linasbot for the app, and nginx error logs for the proxy. Database checks use a
          read-only role limited to pg_stat_statements. Redis checks use an ACL user limited to INFO and SLOWLOG.
          Those accounts are created on the server during deploy and are not stored in git.
        </p>
      </header>
      {error && <p className="rounded-lg bg-red-950 p-3 text-sm text-red-200">{error}</p>}
      {!health && !error ? <p className="text-sm text-slate-400">Checking…</p> : null}
      {health ? (
        <pre className="overflow-auto rounded-xl border border-slate-800 bg-slate-950 p-4 text-xs">{JSON.stringify(health, null, 2)}</pre>
      ) : null}
    </div>
  );
}
