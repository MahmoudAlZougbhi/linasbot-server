import { useEffect, useState } from 'react';
import { ownerApi } from './ownerApi';

/** @param {any} detail */
function StageList({ detail }) {
  const stages = detail?.flow || [];
  if (!stages.length) {
    return <p className="text-sm text-slate-500">No stage timeline stored for this turn yet.</p>;
  }
  return (
    <ol className="space-y-3">
      {stages.map((/** @type {any} */ stage, /** @type {number} */ index) => (
        <li key={`${stage.stage}-${stage.at}-${index}`} className="rounded-lg border border-slate-800 bg-slate-950 p-3">
          <p className="text-sm font-medium text-teal-300">
            {index + 1}. {stage.title || stage.stage}
          </p>
          {stage.at ? <p className="mt-1 text-xs text-slate-500">{stage.at}</p> : null}
          {stage.detail?.ms != null ? (
            <p className="mt-1 text-xs text-slate-400">Took {stage.detail.ms} ms</p>
          ) : null}
          {Array.isArray(stage.detail?.plan_tasks) && stage.detail.plan_tasks.length ? (
            <p className="mt-2 text-xs text-slate-300">
              Tasks: {stage.detail.plan_tasks.map((/** @type {any} */ task) => task.type || task.id).join(', ')}
            </p>
          ) : null}
          {Array.isArray(stage.detail?.evidence) && stage.detail.evidence.length ? (
            <ul className="mt-2 space-y-1 text-xs text-slate-400">
              {stage.detail.evidence.map((/** @type {any} */ item) => (
                <li key={item.id}>
                  [{item.family}] {item.title}: {item.preview}
                </li>
              ))}
            </ul>
          ) : null}
          {stage.detail?.known_usd != null || stage.detail?.cost_pending_events != null ? (
            <p className="mt-2 text-xs text-amber-200">
              Cost: pending events {stage.detail.cost_pending_events ?? 0} · known ${stage.detail.known_usd ?? '0'}
            </p>
          ) : null}
        </li>
      ))}
    </ol>
  );
}

export default function OwnerMessages() {
  const [tenantId, setTenantId] = useState('');
  const [rows, setRows] = useState(/** @type {any[]} */ ([]));
  const [selected, setSelected] = useState(/** @type {any} */ (null));
  const [error, setError] = useState('');

  async function loadList() {
    setError('');
    try {
      const data = await ownerApi.messageFlows({ tenant_id: tenantId.trim(), limit: 80 });
      setRows(data.messages || []);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }

  useEffect(() => {
    void loadList();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- initial load
  }, []);

  async function openRow(/** @type {any} */ row) {
    setError('');
    try {
      const data = await ownerApi.messageFlow(row.tenant_id, row.operation_id);
      setSelected(data.message);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }

  return (
    <div className="space-y-7">
      <header>
        <h2 className="text-2xl font-semibold">Message flow</h2>
        <p className="mt-1 text-sm text-slate-400">
          Every Brain turn by tenant and channel. Open a row to see stages: receive → understand →
          search → evidence sent to AI → reply → cost. No code dumps.
        </p>
      </header>
      {error ? (
        <p role="alert" className="rounded-lg bg-red-950 p-3 text-sm text-red-200">
          {error}
        </p>
      ) : null}
      <section className="flex flex-wrap gap-2">
        <input
          className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
          placeholder="filter tenant id (optional)"
          value={tenantId}
          onChange={(event) => setTenantId(event.target.value)}
        />
        <button type="button" onClick={() => void loadList()} className="rounded bg-teal-500 px-3 py-2 text-slate-950">
          Refresh
        </button>
      </section>
      <section className="grid gap-5 lg:grid-cols-2">
        <div className="space-y-2 rounded-xl border border-slate-800 bg-slate-900 p-4">
          <h3 className="font-semibold">Recent messages</h3>
          {(rows || []).map((row) => (
            <button
              key={`${row.tenant_id}:${row.operation_id}`}
              type="button"
              onClick={() => void openRow(row)}
              className="w-full rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-left text-sm hover:border-teal-700"
            >
              <p className="font-medium text-slate-100">
                {row.tenant_id} · {row.channel || 'channel?'} · {row.state}
              </p>
              <p className="mt-1 text-xs text-slate-400">{row.inbound_preview || row.reply_preview || row.operation_id}</p>
              <p className="mt-1 text-xs text-slate-500">
                stages {row.stage_count || 0} · pending cost {row.pending_cost_events || 0} · known $
                {row.known_usd || '0'}
              </p>
            </button>
          ))}
          {(rows || []).length === 0 ? <p className="text-sm text-slate-500">No Brain outbox turns yet.</p> : null}
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
          <h3 className="font-semibold">Turn detail</h3>
          {!selected ? <p className="mt-3 text-sm text-slate-500">Select a message.</p> : null}
          {selected ? (
            <div className="mt-3 space-y-3 text-sm">
              <p>
                {selected.tenant_id} · {selected.channel} · {selected.state}
              </p>
              <p className="text-slate-300">Inbound: {selected.inbound_preview || '—'}</p>
              <p className="text-slate-300">
                Reply: {(selected.reply_messages || []).map((/** @type {any} */ item) => item.text).filter(Boolean).join(' / ') || '—'}
              </p>
              <p className="text-amber-200">
                Billing: {selected.billing?.response_class || '—'} · units {selected.billing?.message_units ?? '—'} ·
                pending cost events {selected.cost?.pending_events ?? 0} · known ${selected.cost?.known_usd || '0'}
              </p>
              {(selected.evidence_sent_to_ai || []).length ? (
                <div>
                  <p className="font-medium text-teal-300">Evidence sent to AI</p>
                  <ul className="mt-1 list-disc pl-5 text-xs text-slate-400">
                    {selected.evidence_sent_to_ai.map((/** @type {any} */ item) => (
                      <li key={item.id}>
                        [{item.family}] {item.title}: {item.preview}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
              <StageList detail={selected} />
              {selected.note ? <p className="text-xs text-slate-500">{selected.note}</p> : null}
            </div>
          ) : null}
        </div>
      </section>
    </div>
  );
}
