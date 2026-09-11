import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ownerApi } from './ownerApi';

/** @param {{ label: string, value?: string | number }} props */
function Metric({ label, value }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
      <p className="text-sm text-slate-400">{label}</p>
      <p className="mt-2 text-2xl font-semibold">{value ?? '—'}</p>
    </div>
  );
}

const emptyFilters = {
  category: '',
  feature: '',
  provider: '',
  model: '',
  environment: '',
  since: '',
  until: '',
  period: '',
};

export default function OwnerCosts() {
  const [searchParams] = useSearchParams();
  const [dashboard, setDashboard] = useState(/** @type {any} */ (null));
  const [tenantId, setTenantId] = useState(searchParams.get('tenant') || '');
  const [tenant, setTenant] = useState(/** @type {any} */ (null));
  const [ledger, setLedger] = useState(/** @type {any} */ (null));
  const [dryRun, setDryRun] = useState(/** @type {any} */ (null));
  const [filters, setFilters] = useState(emptyFilters);
  const [error, setError] = useState('');

  useEffect(() => {
    let live = true;
    ownerApi
      .costs(filters)
      .then((data) => live && setDashboard(data.dashboard))
      .catch((reason) => live && setError(reason.message));
    return () => {
      live = false;
    };
  }, [filters]);

  useEffect(() => {
    const fromQuery = (searchParams.get('tenant') || '').trim();
    if (!fromQuery) return;
    setTenantId(fromQuery);
    setError('');
    Promise.all([ownerApi.tenantCosts(fromQuery, filters), ownerApi.messageLedger(fromQuery)])
      .then(([data, ledgerData]) => {
        setTenant(data.dashboard);
        setLedger(ledgerData);
      })
      .catch((reason) => setError(reason instanceof Error ? reason.message : String(reason)));
  }, [searchParams, filters]);

  async function loadTenant(id = tenantId) {
    const tid = String(id || '').trim();
    if (!tid) return;
    setError('');
    try {
      const [data, ledgerData] = await Promise.all([
        ownerApi.tenantCosts(tid, filters),
        ownerApi.messageLedger(tid),
      ]);
      setTenantId(tid);
      setTenant(data.dashboard);
      setLedger(ledgerData);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }

  const categories = dashboard?.by_category || {};
  const messages = dashboard?.messages || {};
  return (
    <div className="space-y-7">
      <header>
        <h2 className="text-2xl font-semibold">Provider costs</h2>
        <p className="mt-1 text-sm text-slate-400">
          Expense journal attributed per tenant_id. Pending events are the testing signal; Known USD
          stays 0 until invoice finalization (no invented prices). Message ledger is separate from
          provider USD.
        </p>
        {dashboard?.attribution_note ? (
          <p className="mt-2 text-sm text-teal-300/90">{dashboard.attribution_note}</p>
        ) : null}
      </header>
      {error ? (
        <p role="alert" className="rounded-lg bg-red-950 p-3 text-sm text-red-200">
          {error}
        </p>
      ) : null}
      <section className="grid gap-2 sm:grid-cols-2 xl:grid-cols-5">
        {Object.entries(emptyFilters).map(([name]) =>
          name === 'period' ? (
            <select
              key={name}
              className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
              value={filters.period}
              onChange={(event) => setFilters((current) => ({ ...current, period: event.target.value }))}
            >
              <option value="">all</option>
              <option value="today">today</option>
              <option value="yesterday">yesterday</option>
              <option value="last_7_days">last_7_days</option>
              <option value="last_30_days">last_30_days</option>
            </select>
          ) : (
            <input
              key={name}
              className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
              placeholder={name}
              value={filters[name]}
              onChange={(event) => setFilters((current) => ({ ...current, [name]: event.target.value }))}
            />
          ),
        )}
      </section>
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Metric label="Pending / unpriced (primary)" value={dashboard?.pending_or_unpriced} />
        <Metric label="Known USD (finalized only)" value={dashboard?.known_usd} />
        <Metric label="Message billing" value={messages.message_billing_active ? 'on' : 'off'} />
        <Metric label="Messages remaining (ledger)" value={messages.remaining} />
        <Metric label="Generative settled units" value={dashboard?.usage_classes?.generative?.settled_units} />
        <Metric label="FAQ / static turns" value={dashboard?.usage_classes?.faq_or_static?.count} />
        <Metric
          label="Pending settlements"
          value={
            dashboard?.pending_settlements
              ? `${dashboard.pending_settlements.pending_settlement || 0} hold · ${dashboard.pending_settlements.unresolved || 0} review`
              : '—'
          }
        />
        <Metric
          label="Brain outbox"
          value={
            dashboard?.outbox
              ? `${dashboard.outbox.accepted || 0} accepted · ${dashboard.outbox.pending_settlement || 0} settle`
              : '—'
          }
        />
      </section>
      <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
        <h3 className="font-semibold">Pending by category / provider</h3>
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          {Object.entries(dashboard?.pending_by_category || {}).map(([name, count]) => (
            <p key={`pc-${name}`} className="text-sm text-slate-300">
              {name}: {count}
            </p>
          ))}
          {Object.entries(dashboard?.pending_by_provider || {}).map(([name, count]) => (
            <p key={`pp-${name}`} className="text-sm text-slate-400">
              {name}: {count}
            </p>
          ))}
          {!Object.keys(dashboard?.pending_by_category || {}).length ? (
            <p className="text-sm text-slate-500">No pending provider events yet.</p>
          ) : null}
        </div>
        <h3 className="mt-5 font-semibold">Tenants with expense activity</h3>
        <div className="mt-3 space-y-2">
          {(dashboard?.tenants || []).map((row) => (
            <button
              key={row.tenant_id}
              type="button"
              onClick={() => void loadTenant(row.tenant_id)}
              className="flex w-full items-center justify-between rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-left text-sm hover:border-teal-700"
            >
              <span>{row.tenant_id}</span>
              <span className="text-slate-400">
                pending {row.pending} · events {row.event_count} · known ${row.known_usd}
                {row.top_category ? ` · ${row.top_category}` : ''}
              </span>
            </button>
          ))}
          {(dashboard?.tenants || []).length === 0 ? (
            <p className="text-sm text-slate-500">No tenant expense rows yet.</p>
          ) : null}
        </div>
        <h3 className="mt-5 font-semibold">Recent events</h3>
        <div className="mt-3 max-h-56 space-y-1 overflow-auto text-xs text-slate-400">
          {(dashboard?.events || []).slice(0, 40).map((event) => (
            <p key={event.event_id || `${event.tenant_id}-${event.operation_id}-${event.category}`}>
              {event.tenant_id} · {event.status} · {event.category}/{event.feature} · {event.provider}{' '}
              {event.model} · op {event.operation_id || '—'} · {event.amount_usd ?? 'unpriced'}
            </p>
          ))}
        </div>
        <h3 className="mt-5 font-semibold">Known USD by category (finalized only)</h3>
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          {Object.entries(categories).map(([name, amount]) => (
            <p key={name} className="text-sm text-slate-300">
              {name}: {amount}
            </p>
          ))}
          {Object.keys(categories).length === 0 ? <p className="text-sm text-slate-500">None finalized.</p> : null}
        </div>
      </section>
      <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
        <h3 className="font-semibold">Tenant detail</h3>
        <div className="mt-3 flex flex-wrap gap-2">
          <input
            className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
            placeholder="tenant id"
            value={tenantId}
            onChange={(event) => setTenantId(event.target.value)}
          />
          <button type="button" onClick={() => void loadTenant()} className="rounded bg-teal-500 px-3 py-2 text-slate-950">
            Open
          </button>
          <button
            type="button"
            onClick={() => {
              ownerApi
                .conversionDryRun()
                .then((data) => setDryRun(data.dry_run))
                .catch((reason) => setError(reason instanceof Error ? reason.message : String(reason)));
            }}
            className="rounded border border-slate-600 px-3 py-2 text-sm"
          >
            Credit inventory
          </button>
        </div>
        {dryRun ? (
          <p className="mt-3 text-sm text-amber-200">
            Conversion blocked ({dryRun.reason}). Tenants inventoried: {dryRun.tenant_count}.
          </p>
        ) : null}
        {ledger?.health ? (
          <p className="mt-3 text-sm text-slate-300">
            Ledger health: {ledger.health.ok ? 'ok' : 'check'} · remaining {ledger.health.remaining}
          </p>
        ) : null}
        {tenant ? (
          <div className="mt-4 space-y-2 text-sm">
            <p>
              Messages allocated {tenant.messages?.allocated ?? '—'} · used {tenant.messages?.used ?? '—'} ·
              remaining {tenant.messages?.remaining ?? '—'}
            </p>
            <p>
              Known USD: {tenant.known_usd} · status {tenant.cost_status} · pending {tenant.pending_or_unpriced}
            </p>
            <p>{tenant.attribution_note}</p>
            <ul className="mt-2 list-disc pl-5">
              {(tenant.events || []).map((event) => (
                <li key={event.event_id}>
                  {event.created_at} · {event.category} · {event.provider}/{event.model} ·{' '}
                  {event.amount_usd ?? event.status} · {event.operation_id}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </section>
    </div>
  );
}
