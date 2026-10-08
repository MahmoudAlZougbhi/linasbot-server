// @ts-nocheck
import { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { toast } from 'react-hot-toast';
import { ownerApi } from './ownerApi';
import { useLoad } from './lib/useLoad';
import { label } from './lib/labels';
import { statusLabel, statusTone } from './lib/status';
import { paymentLabel } from './ownerLabels';
import { FREE_NOTE_FIELDS, freeDraftFromCatalog, parseOptionalInt, planDraftFromCatalog } from './catalogDraft';
import PageHeader from './ui/PageHeader';
import Card from './ui/Card';
import Badge from './ui/Badge';
import Button from './ui/Button';
import ConfirmDialog from './ui/ConfirmDialog';
import Alert from './ui/Alert';
import OwnerEconomy from './OwnerEconomy';

const PROVIDERS = [
  ['apple', 'Apple App Store'],
  ['google', 'Google Play'],
  ['stripe', 'Stripe'],
  ['annual_offers', 'Annual offers'],
  ['topup_packs', 'Top-up packs'],
];

function blockerLine(value) {
  if (!value) return '';
  const text = paymentLabel(String(value));
  if (/cutover|token pack/i.test(text)) return '';
  return text;
}

export default function OwnerCatalog() {
  const location = useLocation();
  const pricing = location.pathname.endsWith('/economy');
  const state = useLoad(() => ownerApi.messageCatalog(), []);
  const catalog = state.data?.catalog;
  const [planDrafts, setPlanDrafts] = useState(/** @type {any} */ (null));
  const [freeDraft, setFreeDraft] = useState(/** @type {any} */ (null));
  const [packs, setPacks] = useState(/** @type {any[] | null} */ (null));
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [publish, setPublish] = useState(false);
  const plans = planDrafts || planDraftFromCatalog(catalog);
  const free = freeDraft || freeDraftFromCatalog(catalog);
  const packRows = packs || catalog?.topup_packs || [];

  async function saveDraft() {
    setSaving(true);
    setError('');
    try {
      const dailyLimit = parseOptionalInt(catalog?.ai_setup_daily_edit_limit, 'Daily AI Setup edit limit');
      /** @type {Record<string, unknown>} */
      const freePayload = {};
      const allowance = parseOptionalInt(free.included_messages, 'Free included messages');
      if (allowance !== undefined) freePayload.included_messages = allowance;
      /** @type {Record<string, string>} */
      const configured = {};
      for (const field of FREE_NOTE_FIELDS) {
        const value = String(free.configured?.[field] ?? '').trim();
        if (value) configured[field] = value;
      }
      if (Object.keys(configured).length) freePayload.configured = configured;
      const data = await ownerApi.updateMessageCatalog({
        ...(dailyLimit !== undefined ? { ai_setup_daily_edit_limit: dailyLimit } : {}),
        ...(Object.keys(freePayload).length ? { free: freePayload } : {}),
        plans,
        topup_packs: Object.fromEntries(packRows.map((pack) => [pack.pack_id, { product_id: pack.product_id || '', usd: pack.usd, quantity: pack.quantity, sale_ready: pack.sale_ready }])),
        reason: 'portal_edit',
      });
      setPlanDrafts(planDraftFromCatalog(data.catalog));
      setFreeDraft(freeDraftFromCatalog(data.catalog));
      setPacks(data.catalog?.topup_packs || []);
      toast.success('Saved');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Save failed');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Plans & prices" subtitle="Set plan prices and message limits. Customers see them only after you publish." />
      <div role="tablist" aria-label="Pricing" className="flex gap-2">
        <Link role="tab" aria-selected={!pricing} to="/owner/catalog" className={`border-b-2 px-3 py-2 text-sm ${pricing ? 'border-transparent text-slate-700' : 'border-[#0F766E] bg-[#F0FDFA] text-[#0F766E]'}`}>Plans</Link>
        <Link role="tab" aria-selected={pricing} to="/owner/economy" className={`border-b-2 px-3 py-2 text-sm ${pricing ? 'border-[#0F766E] bg-[#F0FDFA] text-[#0F766E]' : 'border-transparent text-slate-700'}`}>Message pricing</Link>
      </div>
      {pricing ? <OwnerEconomy embedded /> : null}
      {!pricing && (state.status === 'error' || error) ? <Alert title="We couldn't load plans." detail={error || state.error} /> : null}
      {!pricing && catalog ? (
        <>
          <Card title="Status" action={<Button variant="secondary" onClick={() => setPublish(true)}>Publish prices…</Button>}>
            <Badge tone={statusTone('published', catalog.published)}>{statusLabel('published', catalog.published)}</Badge>
            <p className="mt-2 text-sm text-slate-700">{catalog.published ? 'Published. These prices are live.' : 'Draft, not published. Customers still buy the current store plans.'}</p>
          </Card>
          <Card title="Paid plans">
            {(catalog.plans || []).map((plan) => (
              <div key={plan.plan_id} className="mt-4 grid items-end gap-3 md:grid-cols-[160px_140px_180px_160px_auto]">
                <span className="text-sm font-medium">{label('plan', plan.plan_id)}</span>
                <label className="text-sm">Price (USD / month)
                  <input aria-label={`${plan.plan_id} price`} className="mt-1 h-9 w-full rounded-lg border border-[#7C8798] px-3 text-right" value={plans[plan.plan_id]?.intended_price_usd ?? ''} onChange={(event) => setPlanDrafts({ ...plans, [plan.plan_id]: { ...plans[plan.plan_id], intended_price_usd: event.target.value } })} />
                </label>
                <label className="text-sm">Messages included per month
                  <input aria-label={`${plan.plan_id} messages`} className="mt-1 h-9 w-full rounded-lg border border-[#7C8798] px-3 text-right" value={plans[plan.plan_id]?.included_messages ?? ''} onChange={(event) => setPlanDrafts({ ...plans, [plan.plan_id]: { ...plans[plan.plan_id], included_messages: event.target.value } })} />
                </label>
                <label className="text-sm">Ready-answer limit
                  <input aria-label={`${plan.plan_id} ready answers`} className="mt-1 h-9 w-full rounded-lg border border-[#7C8798] px-3 text-right" value={plans[plan.plan_id]?.faq_capacity ?? ''} onChange={(event) => setPlanDrafts({ ...plans, [plan.plan_id]: { ...plans[plan.plan_id], faq_capacity: event.target.value } })} />
                </label>
                <span className="justify-self-start"><Badge tone={statusTone('planLive', plan.checkout_ready)}>{statusLabel('planLive', plan.checkout_ready)}</Badge></span>
              </div>
            ))}
          </Card>
          <Card title="Free plan">
            {/* leave empty until decided */}
            <label className="block text-sm">Free messages per month
              <input placeholder="Not set yet, e.g. 50" className="mt-1 h-9 w-full rounded-lg border border-[#7C8798] px-3" value={free.included_messages} onChange={(event) => setFreeDraft({ ...free, included_messages: event.target.value })} />
            </label>
            {FREE_NOTE_FIELDS.map((field) => (
              <label key={field} className="mt-3 block text-sm">{label('freeField', field)}
                <input placeholder="Not set yet" className="mt-1 h-9 w-full rounded-lg border border-[#7C8798] px-3" value={free.configured[field] || ''} onChange={(event) => setFreeDraft({ ...free, configured: { ...free.configured, [field]: event.target.value } })} />
                {field === 'credit_to_message_conversion' ? <span className="mt-1 block text-[13px] text-slate-600">A written note. The number used for conversion is on Message pricing.</span> : null}
              </label>
            ))}
          </Card>
          <Card title="Payment providers">
            {PROVIDERS.map(([key, name]) => {
              const row = catalog.payment_readiness?.[key] || {};
              const status = row.status || '';
              const note = blockerLine(row.blocker);
              return (
                <div key={key} className="mt-3 flex flex-wrap items-center gap-3">
                  <span className="min-w-40 text-sm font-medium">{name}</span>
                  <Badge tone={statusTone('payment', status)}>{status ? statusLabel('payment', status) : 'Not set up'}</Badge>
                  {note ? <span className="text-sm text-slate-700">{note}</span> : null}
                </div>
              );
            })}
          </Card>
          <Button onClick={() => { void saveDraft(); }} loading={saving}>{saving ? 'Saving…' : 'Save changes'}</Button>
          <details className="rounded-xl border border-slate-200 bg-white p-5">
            <summary className="cursor-pointer text-base font-semibold">Advanced settings</summary>
            <div className="mt-4 overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="text-left text-slate-600"><th>Pack</th><th>Quantity</th><th>Price (USD)</th><th>Store product ID</th><th>For sale</th></tr></thead>
                <tbody>
                  {packRows.map((pack, index) => (
                    <tr key={pack.pack_id}>
                      <td>{pack.quantity ? `${pack.quantity} messages` : 'Pack'}</td>
                      <td>{pack.quantity}</td>
                      <td>{pack.usd ?? '—'}</td>
                      <td><input aria-label={`${pack.pack_id} store product`} className="h-9 rounded-lg border border-[#7C8798] px-2" value={pack.product_id || ''} onChange={(event) => setPacks(packRows.map((item, itemIndex) => itemIndex === index ? { ...item, product_id: event.target.value } : item))} /></td>
                      <td>{pack.sale_ready ? 'Yes' : 'No'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <form className="mt-4 grid max-w-xl gap-3" onSubmit={(event) => { event.preventDefault(); const form = new FormData(event.currentTarget); void ownerApi.patchDailyEdits({ tenant_id: String(form.get('tenant') || ''), limit: Number(form.get('limit') || 0), reason: 'portal_edit' }).then(() => toast.success('Saved')).catch((reason) => setError(reason.message)); }}>
              <label className="text-sm">Business
                <input name="tenant" aria-label="Business" className="mt-1 h-9 w-full rounded-lg border border-[#7C8798] px-3 text-sm" />
              </label>
              <label className="text-sm">Daily AI setup edits allowed
                <input name="limit" aria-label="Daily AI setup edits allowed" className="mt-1 h-9 w-32 rounded-lg border border-[#7C8798] px-3 text-sm" />
              </label>
              <p className="text-[13px] text-slate-600">Overrides the daily limit for this business only.</p>
              <Button type="submit" variant="secondary">Save limit</Button>
            </form>
          </details>
        </>
      ) : null}
      {publish ? <ConfirmDialog title="Publish plans & prices?" body="Customers will see these prices. You can still edit them later." confirmLabel="Publish" onClose={() => setPublish(false)} onConfirm={async () => { await ownerApi.publishMessageCatalog(); setPublish(false); }} /> : null}
    </div>
  );
}
