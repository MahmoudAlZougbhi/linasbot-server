import { useEffect, useState } from 'react';
import { ownerApi } from './ownerApi';

export default function OwnerAudit() {
  const [events, setEvents] = useState(/** @type {any[]} */ ([]));
  const [error, setError] = useState('');

  useEffect(() => {
    ownerApi.audit().then((data) => setEvents(data.events || [])).catch((reason) => setError(reason.message));
  }, []);

  return (
    <div className="space-y-6">
      <header>
        <h2 className="text-2xl font-semibold">Audit log</h2>
        <p className="mt-1 text-sm text-slate-400">Catalog edits and publishes recorded for the platform owner.</p>
      </header>
      {error && <p className="rounded-lg bg-red-950 p-3 text-sm text-red-200">{error}</p>}
      {events.length === 0 ? <p className="text-sm text-slate-400">No audit events yet.</p> : null}
      <ul className="space-y-2">
        {events.map((event, index) => (
          <li key={`${event.at || index}`} className="rounded-lg border border-slate-800 p-3 text-sm">
            <p className="text-teal-300">{event.action || event.kind || 'event'}</p>
            <p className="mt-1 text-slate-400">{event.at || event.updated_at || ''}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}
