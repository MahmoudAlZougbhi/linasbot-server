import { useEffect, useState } from 'react';
import { ownerApi } from './ownerApi';

export default function OwnerTraces() {
  const [traces, setTraces] = useState(/** @type {any[]} */ ([]));
  const [selected, setSelected] = useState(/** @type {any} */ (null));
  const [tenantId, setTenantId] = useState('');
  const [brain, setBrain] = useState('');
  const [error, setError] = useState('');

  const load = () => {
    ownerApi.listTraces({ tenant_id: tenantId, brain })
      .then((data) => setTraces(data.traces || []))
      .catch((reason) => setError(reason.message));
  };

  useEffect(() => { load(); }, []);

  return (
    <div className="space-y-6">
      <header>
        <h2 className="text-2xl font-semibold">Message traces</h2>
        <p className="mt-1 text-sm text-slate-400">Every customer and copilot turn, including what was retrieved and what the model was given.</p>
      </header>
      <div className="flex flex-wrap gap-2">
        <input value={tenantId} onChange={(event) => setTenantId(event.target.value)} placeholder="Tenant" className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm" />
        <select value={brain} onChange={(event) => setBrain(event.target.value)} className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm">
          <option value="">All brains</option>
          <option value="customer">Customer</option>
          <option value="owner_copilot">Owner copilot</option>
        </select>
        <button type="button" onClick={load} className="rounded-lg bg-slate-800 px-3 py-2 text-sm">Filter</button>
      </div>
      {error && <p className="rounded-lg bg-red-950 p-3 text-sm text-red-200">{error}</p>}
      {traces.length === 0 ? <p className="text-sm text-slate-400">No traces yet. Send a message and refresh.</p> : null}
      <div className="grid gap-4 lg:grid-cols-2">
        <ul className="space-y-2">
          {traces.map((trace) => (
            <li key={trace.id}>
              <button type="button" onClick={() => setSelected(trace)} className="w-full rounded-lg border border-slate-800 p-3 text-left text-sm hover:bg-slate-900">
                <span className="text-teal-300">{trace.brain}</span> · {trace.channel} · {trace.tenant_id || 'platform'}
                <span className="mt-1 block text-slate-400">{trace.created_at} · {trace.has_error ? 'error' : 'ok'}</span>
              </button>
            </li>
          ))}
        </ul>
        {selected ? (
          <pre className="overflow-auto rounded-xl border border-slate-800 bg-slate-950 p-4 text-xs text-slate-200">
            {JSON.stringify(selected.payload || selected, null, 2)}
          </pre>
        ) : null}
      </div>
    </div>
  );
}
