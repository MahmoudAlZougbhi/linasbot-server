import { useEffect, useState } from 'react';
import OwnerActivationBanner from './OwnerActivationBanner';
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
  const [dashboard, setDashboard] = useState(/** @type {any} */ (null));
  const [tenantId, setTenantId] = useState('');
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

  async function loadTenant() {
    if (!tenantId.trim()) return;
    setError('');
    try {
      const [data, ledgerData] = await Promise.all([
        ownerApi.tenantCosts(tenantId.trim(), filters),
        ownerApi.messageLedger(tenantId.trim()),
      ]);
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
          Internal expense journal. These dollars are not billed to tenants as messages. Translation
          is a separate category and is not added into LLM totals. Environment defaults to all
          recorded rows; production expenses are stamped prod, not test. Message remaining on this
          page is ledger rows for operators — tenants do not see remaining until message billing is
          on.
        </p>
      </header>
      <OwnerActivationBanner />
      {error && (
        <p role="alert" className="rounded-lg bg-red-950 p-3 text-sm text-red-200">
          {error}
        </p>
      )}
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
      {messages.note ? <p className="text-sm text-slate-400">{messages.note}</p> : null}
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Metric label="Ledger store" value={dashboard?.store} />
        <Metric label="Expense environment" value={dashboard?.environment || 'all'} />
        <Metric label="Known USD" value={dashboard?.known_usd} />
        <Metric label="Tenant USD" value={dashboard?.tenant_known_usd} />
        <Metric label="Platform / shared" value={dashboard?.platform_shared_usd} />
        <Metric label="Pending / unpriced" value={dashboard?.pending_or_unpriced} />
        <Metric label="Message billing" value={messages.message_billing_active ? 'on' : 'off'} />
        <Metric label="Messages allocated (ledger)" value={messages.allocated} />
        <Metric label="Messages used (ledger)" value={messages.used} />
        <Metric label="Messages reserved (ledger)" value={messages.reserved} />
        <Metric label="Messages remaining (ledger)" value={messages.remaining} />
        <Metric
          label="Pending settlements"
          value={
            dashboard?.pending_settlements
              ? `${dashboard.pending_settlements.pending_settlement || 0} hold · ${dashboard.pending_settlements.unresolved || 0} review`
              : '—'
          }
        />
        <Metric
          label="Legacy credit holds (not messages)"
          value={
            dashboard?.leftover_credit_holds
              ? `${dashboard.leftover_credit_holds.open || 0} open · ${dashboard.leftover_credit_holds.stale || 0} stale`
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
        <Metric
          label="Processing budgets"
          value={
            dashboard?.processing_budgets
              ? `${dashboard.processing_budgets.daily_attempts}/${dashboard.processing_budgets.daily_attempt_limit} attempts`
              : '—'
          }
        />
        <Metric
          label="Generative messages"
          value={dashboard?.usage_classes?.generative?.settled_units ?? dashboard?.usage_classes?.generative?.units}
        />
        <Metric
          label="FAQ / static turns"
          value={dashboard?.usage_classes?.faq_or_static?.count}
        />
        <Metric
          label="Daily edits used"
          value={
            dashboard?.daily_edits
              ? `${dashboard.daily_edits.used} · ${dashboard.daily_edits.tenants_at_limit || 0} at limit`
              : '—'
          }
        />
      </section>
      <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
        <h3 className="font-semibold">By category</h3>
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          {Object.entries(categories).map(([name, amount]) => (
            <p key={name} className="text-sm text-slate-300">
              {name}: {amount}
            </p>
          ))}
          {Object.keys(categories).length === 0 ? <p className="text-sm text-slate-500">No events yet.</p> : null}
        </div>
        <h3 className="mt-5 font-semibold">By feature</h3>
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          {Object.entries(dashboard?.by_feature || {}).map(([name, amount]) => (
            <p key={`f-${name}`} className="text-sm text-slate-300">
              {name}: {amount}
            </p>
          ))}
        </div>
        <h3 className="mt-5 font-semibold">By response class</h3>
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          {Object.entries(dashboard?.usage_classes?.by_class || {}).map(([name, row]) => (
            <p key={`c-${name}`} className="text-sm text-slate-300">
              {name}: {row.settled_units ?? row.units ?? 0} settled · {row.count ?? 0} turns
            </p>
          ))}
          {Object.keys(dashboard?.usage_classes?.by_class || {}).length === 0 ? (
            <p className="text-sm text-slate-500">No ledger classes yet.</p>
          ) : null}
        </div>
        <h3 className="mt-5 font-semibold">Daily edits by tenant</h3>
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          {(dashboard?.daily_edits?.tenants || []).map((row) => (
            <p key={row.tenant_id} className="text-sm text-slate-300">
              {row.tenant_id}: {row.used}/{row.limit} used · {row.remaining} remaining
            </p>
          ))}
          {(dashboard?.daily_edits?.tenants || []).length === 0 ? (
            <p className="text-sm text-slate-500">No tenant edit rows yet.</p>
          ) : null}
        </div>
        <h3 className="mt-5 font-semibold">By provider / model</h3>
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          {Object.entries(dashboard?.by_provider || {}).map(([name, amount]) => (
            <p key={`p-${name}`} className="text-sm text-slate-300">
              {name}: {amount}
            </p>
          ))}
          {Object.entries(dashboard?.by_model || {}).map(([name, amount]) => (
            <p key={`m-${name}`} className="text-sm text-slate-400">
              {name}: {amount}
            </p>
          ))}
        </div>
      </section>
      <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
        <h3 className="font-semibold">Tenant detail</h3>
        <div className="mt-3 flex gap-2">
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
            Conversion blocked ({dryRun.reason}). Tenants inventoried: {dryRun.tenant_count}. Rate is not assumed.
          </p>
        ) : null}
        {ledger?.health ? (
          <p className="mt-3 text-sm text-slate-300">
            Ledger health: {ledger.health.ok ? 'ok' : 'check'} · store {ledger.health.store || tenant?.store || '—'} ·
            remaining {ledger.health.remaining} · stale included {(ledger.health.stale_included || []).length}
          </p>
        ) : null}
        {tenant ? (
          <div className="mt-4 space-y-2 text-sm">
            <p>
              Messages allocated {tenant.messages?.allocated ?? '—'} · used {tenant.messages?.used ?? '—'} ·
              remaining {tenant.messages?.remaining ?? '—'} · reserved {tenant.messages?.reserved ?? '—'}
            </p>
            <p>
              Generative settled {tenant.usage_classes?.generative?.settled_units ?? 0} · FAQ/static turns{' '}
              {tenant.usage_classes?.faq_or_static?.count ?? 0} (0 message units)
            </p>
            <p>
              Known USD: {tenant.known_usd} · status {tenant.cost_status} · pending {tenant.pending_or_unpriced}
            </p>
            <p>Top category: {tenant.top_category || '—'}</p>
            <p>
              Daily edits: {tenant.daily_edits?.used}/{tenant.daily_edits?.limit} used, reset {tenant.daily_edits?.reset_at}
            </p>
            <p>
              Processing: {tenant.processing_budgets?.daily_attempts ?? 0}/
              {tenant.processing_budgets?.daily_attempt_limit ?? 0} attempts · concurrent{' '}
              {tenant.processing_budgets?.concurrent ?? 0}
            </p>
            <p>
              Pending settlements: {tenant.pending_settlements?.pending_settlement ?? 0} · unresolved{' '}
              {tenant.pending_settlements?.unresolved ?? 0}
            </p>
            <p>
              Legacy credit holds (not messages): {tenant.leftover_credit_holds?.open ?? 0} open ·{' '}
              {tenant.leftover_credit_holds?.stale ?? 0} stale
            </p>
            <ul className="mt-2 list-disc pl-5">
              {(tenant.events || []).map((event) => (
                <li key={event.event_id}>
                  {event.created_at} · {event.category} · {event.provider}/{event.model} · {event.amount_usd ?? event.status} · {event.feature} · {event.operation_id}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </section>
    </div>
  );
}
