// @ts-nocheck
import { useState } from 'react';
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
import TechDetails from './ui/TechDetails';

export default function OwnerCatalog() {
  const state = useLoad(() => ownerApi.messageCatalog(), []);
  const catalog = state.data?.catalog;
  const [planDrafts, setPlanDrafts] = useState(/** @type {any} */ (null));
  const [freeDraft, setFreeDraft] = useState(/** @type {any} */ (null));
  const [limit] = useState('');
  const [error, setError] = useState('');
  const [publish, setPublish] = useState(false);
  const plans = planDrafts || planDraftFromCatalog(catalog);
  const free = freeDraft || freeDraftFromCatalog(catalog);

  async function saveDraft() {
    const dailyLimit = parseOptionalInt(limit || catalog?.ai_setup_daily_edit_limit, 'Daily AI Setup edit limit');
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
      topup_packs: Object.fromEntries((catalog?.topup_packs || []).map((pack) => [pack.pack_id, { product_id: pack.product_id || '' }])),
      reason: 'portal_edit',
    });
    setPlanDrafts(planDraftFromCatalog(data.catalog));
    setFreeDraft(freeDraftFromCatalog(data.catalog));
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Plans & prices" subtitle="Set plan prices and message limits. Customers see them only after you publish." />
      {state.status === 'error' || error ? <Alert title="We couldn't load plans." detail={error || state.error} /> : null}
      {catalog ? (
        <>
          <Card title="Status" action={<Button variant="secondary" onClick={() => setPublish(true)}>Publish prices…</Button>}>
            <Badge tone={statusTone('published', catalog.published)}>{statusLabel('published', catalog.published)}</Badge>
            <p className="mt-2 text-sm text-slate-700">{catalog.published ? 'Published. These prices are live.' : 'Draft, not published. Customers still buy the current store plans.'}</p>
          </Card>
          <Card title="Paid plans">
            {(catalog.plans || []).map((plan) => (
              <div key={plan.plan_id} className="mt-3 grid gap-2 sm:grid-cols-3">
                <span className="text-sm font-medium">{label('plan', plan.plan_id)}</span>
                <input aria-label={`${plan.plan_id} price`} className="h-9 rounded-lg border border-[#7C8798] px-3" value={plans[plan.plan_id]?.intended_price_usd ?? ''} onChange={(event) => setPlanDrafts({ ...plans, [plan.plan_id]: { ...plans[plan.plan_id], intended_price_usd: event.target.value } })} />
                <Badge tone={statusTone('planLive', plan.checkout_ready)}>{statusLabel('planLive', plan.checkout_ready)}</Badge>
              </div>
            ))}
          </Card>
          <Card title="Free plan">
            <label className="block text-sm">Free messages per month
              <input className="mt-1 h-9 w-full rounded-lg border border-[#7C8798] px-3" value={free.included_messages} onChange={(event) => setFreeDraft({ ...free, included_messages: event.target.value })} />
            </label>
            {FREE_NOTE_FIELDS.map((field) => (
              <label key={field} className="mt-3 block text-sm">{label('freeField', field)}
                <input className="mt-1 h-9 w-full rounded-lg border border-[#7C8798] px-3" value={free.configured[field] || ''} onChange={(event) => setFreeDraft({ ...free, configured: { ...free.configured, [field]: event.target.value } })} />
              </label>
            ))}
          </Card>
          <Card title="Payment providers">
            <p className="text-sm">Apple App Store: {paymentLabel('implemented')}</p>
            <p className="text-sm">Stripe: {paymentLabel('retired_token_packs')}</p>
            <TechDetails text={JSON.stringify(catalog.payment_readiness || {})} />
          </Card>
          <Button onClick={() => { void saveDraft().catch((reason) => setError(reason.message)); }}>Save changes</Button>
        </>
      ) : null}
      {publish ? <ConfirmDialog title="Publish plans & prices?" body="Customers will see these prices. You can still edit them later." confirmLabel="Publish" onClose={() => setPublish(false)} onConfirm={async () => { await ownerApi.publishMessageCatalog(); setPublish(false); }} /> : null}
    </div>
  );
}
