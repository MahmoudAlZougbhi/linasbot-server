import { useEffect, useState } from 'react';
import { ownerApi } from './ownerApi';

function parseOptionalInt(raw, label) {
  const text = String(raw ?? '').trim();
  if (!text) return undefined;
  if (!/^-?\d+$/.test(text)) {
    throw new Error(`${label} must be an integer`);
  }
  return Number(text);
}

/** @param {any} catalog */
function planDraftFromCatalog(catalog) {
  const rows = {};
  for (const plan of catalog?.plans || []) {
    rows[plan.plan_id] = {
      intended_price_usd: plan.intended_price_usd,
      included_messages: plan.included_messages,
      faq_capacity: plan.faq_capacity,
    };
  }
  return rows;
}

/** @param {any} catalog */
function packDraftFromCatalog(catalog) {
  const rows = {};
  for (const pack of catalog?.topup_packs || []) {
    rows[pack.pack_id] = { product_id: pack.product_id || '' };
  }
  return rows;
}

const FREE_NOTE_FIELDS = [
  'free_message_renewal',
  'knowledge_line_budget',
  'services_products_line_budget',
  'content_line_definition',
  'message_topup_prices',
  'credit_to_message_conversion',
];

/** @param {any} catalog */
function freeDraftFromCatalog(catalog) {
  const free = catalog?.free || {};
  const src = free.configured && typeof free.configured === 'object' ? free.configured : {};
  /** @type {Record<string, string>} */
  const configured = {};
  for (const field of FREE_NOTE_FIELDS) {
    configured[field] = src[field] == null ? '' : String(src[field]);
  }
  return {
    included_messages: free.included_messages == null ? '' : String(free.included_messages),
    configured,
  };
}

export default function OwnerCatalog() {
  const [catalog, setCatalog] = useState(/** @type {any} */ (null));
  const [error, setError] = useState('');
  const [limit, setLimit] = useState('30');
  const [planDrafts, setPlanDrafts] = useState(/** @type {Record<string, any>} */ ({}));
  const [packDrafts, setPackDrafts] = useState(/** @type {Record<string, any>} */ ({}));
  const [freeDraft, setFreeDraft] = useState(freeDraftFromCatalog(null));
  const [overrideTenant, setOverrideTenant] = useState('');
  const [overrideLimit, setOverrideLimit] = useState('');

  useEffect(() => {
    let live = true;
    ownerApi
      .messageCatalog()
      .then((data) => {
        if (!live) return;
        setCatalog(data.catalog);
        setLimit(String(data.catalog?.ai_setup_daily_edit_limit ?? 30));
        setPlanDrafts(planDraftFromCatalog(data.catalog));
        setPackDrafts(packDraftFromCatalog(data.catalog));
        setFreeDraft(freeDraftFromCatalog(data.catalog));
      })
      .catch((reason) => live && setError(reason.message));
    return () => {
      live = false;
    };
  }, []);

  async function saveDraft() {
    setError('');
    try {
      const dailyLimit = parseOptionalInt(limit, 'Daily AI Setup edit limit');
      /** @type {Record<string, unknown>} */
      const freePayload = {};
      const allowance = parseOptionalInt(freeDraft.included_messages, 'Free included messages');
      if (allowance !== undefined) freePayload.included_messages = allowance;
      /** @type {Record<string, string>} */
      const configured = {};
      for (const field of FREE_NOTE_FIELDS) {
        const value = String(freeDraft.configured?.[field] ?? '').trim();
        if (value) configured[field] = value;
      }
      if (Object.keys(configured).length) freePayload.configured = configured;
      const data = await ownerApi.updateMessageCatalog({
        ...(dailyLimit !== undefined ? { ai_setup_daily_edit_limit: dailyLimit } : {}),
        ...(Object.keys(freePayload).length ? { free: freePayload } : {}),
        plans: planDrafts,
        topup_packs: packDrafts,
        reason: 'portal_edit',
      });
      setCatalog(data.catalog);
      setPlanDrafts(planDraftFromCatalog(data.catalog));
      setPackDrafts(packDraftFromCatalog(data.catalog));
      setFreeDraft(freeDraftFromCatalog(data.catalog));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }

  async function tryPublish() {
    setError('');
    try {
      const data = await ownerApi.publishMessageCatalog();
      setCatalog(data.catalog);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }

  /** @param {string} planId @param {string} field @param {string} value */
  function editPlan(planId, field, value) {
    setPlanDrafts((current) => ({
      ...current,
      [planId]: { ...current[planId], [field]: value },
    }));
  }

  /** @param {string} packId @param {string} value */
  function editPack(packId, value) {
    setPackDrafts((current) => ({ ...current, [packId]: { product_id: value } }));
  }

  async function saveTenantLimit() {
    setError('');
    try {
      const tenantId = overrideTenant.trim();
      if (!tenantId) throw new Error('Tenant id is required');
      const dailyLimit = parseOptionalInt(overrideLimit, 'Tenant daily-edit limit');
      if (dailyLimit === undefined) throw new Error('Tenant daily-edit limit is required');
      await ownerApi.patchDailyEdits({ tenant_id: tenantId, limit: dailyLimit, reason: 'portal_edit' });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }

  const plans = catalog?.plans || [];
  const packs = catalog?.topup_packs || [];
  const free = catalog?.free || {};
  return (
    <div className="space-y-7">
      <header>
        <h2 className="text-2xl font-semibold">Message catalog</h2>
        <p className="mt-1 text-sm text-slate-400">
          Draft commercial matrix. Checkout stays on the live store catalog until cutover. Paid
          overlays stay draft until Free section-2 values exist and publish succeeds.
        </p>
      </header>
      {error && (
        <p role="alert" className="rounded-lg bg-red-950 p-3 text-sm text-red-200">
          {error}
        </p>
      )}
      <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
        <p className="text-sm text-slate-400">Revision {catalog?.admin_revision || '—'}</p>
        <p className="mt-1 text-sm text-slate-400">Published: {catalog?.published ? 'yes' : 'no'}</p>
        <label className="mt-4 block text-sm text-slate-300">
          Daily AI Setup edit limit
          <input
            className="mt-1 block rounded-lg border border-slate-700 bg-slate-950 px-3 py-2"
            value={limit}
            onChange={(event) => setLimit(event.target.value)}
          />
        </label>
        <div className="mt-4 flex gap-2">
          <button type="button" onClick={() => void saveDraft()} className="rounded bg-teal-500 px-3 py-2 text-slate-950">
            Save draft
          </button>
          <button type="button" onClick={() => void tryPublish()} className="rounded border border-slate-600 px-3 py-2">
            Publish
          </button>
        </div>
        <p className="mt-3 text-sm text-amber-200">
          Free publish blocked until: {(free.unconfigured_fields || []).join(', ') || 'none'}
        </p>
        <div className="mt-4 space-y-3 rounded-lg border border-slate-800 bg-slate-950 p-4">
          <p className="text-sm text-slate-300">Free offer (leave empty until decided — no invented values)</p>
          <label className="block text-sm text-slate-400">
            included_messages
            <input
              className="mt-1 block w-40 rounded border border-slate-700 bg-slate-900 px-2 py-1"
              value={freeDraft.included_messages}
              onChange={(event) =>
                setFreeDraft((current) => ({ ...current, included_messages: event.target.value }))
              }
              placeholder="empty"
            />
          </label>
          {FREE_NOTE_FIELDS.map((field) => (
            <label key={field} className="block text-sm text-slate-400">
              {field}
              <input
                className="mt-1 block w-full rounded border border-slate-700 bg-slate-900 px-2 py-1"
                value={freeDraft.configured?.[field] || ''}
                onChange={(event) =>
                  setFreeDraft((current) => ({
                    ...current,
                    configured: { ...current.configured, [field]: event.target.value },
                  }))
                }
                placeholder="empty until decided"
              />
            </label>
          ))}
        </div>
        <div className="mt-4 space-y-2 rounded-lg border border-slate-800 bg-slate-950 p-4">
          <p className="text-sm text-slate-300">Per-tenant daily-edit override</p>
          <div className="flex flex-wrap gap-2">
            <input
              className="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-sm"
              value={overrideTenant}
              onChange={(event) => setOverrideTenant(event.target.value)}
              placeholder="tenant id"
            />
            <input
              className="w-24 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-sm"
              value={overrideLimit}
              onChange={(event) => setOverrideLimit(event.target.value)}
              placeholder="limit"
            />
            <button
              type="button"
              onClick={() => void saveTenantLimit()}
              className="rounded border border-slate-600 px-3 py-1 text-sm"
            >
              Save tenant limit
            </button>
          </div>
        </div>
        <div className="mt-4 space-y-1 text-sm text-slate-400">
          <p>Apple: {catalog?.payment_readiness?.apple?.status || '—'}</p>
          <p>Google: {catalog?.payment_readiness?.google?.status || '—'} ({catalog?.payment_readiness?.google?.blocker || 'ok'})</p>
          <p>Stripe: {catalog?.payment_readiness?.stripe?.status || '—'}</p>
          <p>Annual offers: {catalog?.payment_readiness?.annual_offers?.status || 'unconfigured'}</p>
        </div>
      </section>
      <section className="overflow-x-auto rounded-xl border border-slate-800">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-slate-900 text-slate-400">
            <tr>
              {['Plan', 'Intended USD / month', 'Messages', 'FAQ', 'Live checkout'].map((label) => (
                <th key={label} className="px-4 py-3">
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800 bg-slate-950">
            {plans.map((plan) => {
              const draft = planDrafts[plan.plan_id] || {};
              return (
                <tr key={plan.plan_id}>
                  <td className="px-4 py-3">{plan.display_name}</td>
                  <td className="px-4 py-3">
                    <input
                      className="w-24 rounded border border-slate-700 bg-slate-900 px-2 py-1"
                      value={draft.intended_price_usd ?? ''}
                      onChange={(event) => editPlan(plan.plan_id, 'intended_price_usd', event.target.value)}
                    />
                  </td>
                  <td className="px-4 py-3">
                    <input
                      className="w-24 rounded border border-slate-700 bg-slate-900 px-2 py-1"
                      value={draft.included_messages ?? ''}
                      onChange={(event) => editPlan(plan.plan_id, 'included_messages', event.target.value)}
                    />
                  </td>
                  <td className="px-4 py-3">
                    <input
                      className="w-20 rounded border border-slate-700 bg-slate-900 px-2 py-1"
                      value={draft.faq_capacity ?? ''}
                      onChange={(event) => editPlan(plan.plan_id, 'faq_capacity', event.target.value)}
                    />
                  </td>
                  <td className="px-4 py-3">{plan.checkout_ready ? 'ready' : 'blocked'}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>
      <section className="overflow-x-auto rounded-xl border border-slate-800">
        <p className="bg-slate-900 px-4 py-3 text-sm text-slate-400">
          Draft message packs. Prices stay empty until section-2 top-up values exist. Mapping a
          store product id does not make a pack sale-ready.
        </p>
        <table className="min-w-full text-left text-sm">
          <thead className="bg-slate-900 text-slate-400">
            <tr>
              {['Pack', 'Quantity', 'USD', 'Store product', 'Sale ready'].map((label) => (
                <th key={label} className="px-4 py-3">
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800 bg-slate-950">
            {packs.map((pack) => (
              <tr key={pack.pack_id}>
                <td className="px-4 py-3">{pack.pack_id}</td>
                <td className="px-4 py-3">{pack.quantity}</td>
                <td className="px-4 py-3">{pack.price_usd ?? 'unpriced'}</td>
                <td className="px-4 py-3">
                  <input
                    className="w-56 rounded border border-slate-700 bg-slate-900 px-2 py-1"
                    value={packDrafts[pack.pack_id]?.product_id || ''}
                    onChange={(event) => editPack(pack.pack_id, event.target.value)}
                    placeholder="store product id"
                  />
                </td>
                <td className="px-4 py-3">{pack.sale_ready ? 'yes' : 'no'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
