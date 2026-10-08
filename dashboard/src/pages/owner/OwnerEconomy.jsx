// @ts-nocheck
import { useEffect, useState } from 'react';
import { ownerApi } from './ownerApi';
import { label } from './lib/labels';
import PageHeader from './ui/PageHeader';
import Card from './ui/Card';
import Button from './ui/Button';
import Alert from './ui/Alert';
import TechDetails from './ui/TechDetails';

function emptyEconomy() {
  return {
    action_costs: { ai_dm_reply: 1, ai_web_chat: 1, ai_whatsapp: 1, ai_tiktok: 1, ai_public_comment: 1, ai_comment_dm: 1, ai_both_mode: 'each', followup_sent: 1 },
    copilot: { confirm_threshold_messages: 2, bands: [] },
    iap_message_quantities: {},
    conversion_rate: '',
  };
}

function economyFromCatalog(catalog) {
  const src = catalog?.economy && typeof catalog.economy === 'object' ? catalog.economy : {};
  const defaults = emptyEconomy();
  return {
    action_costs: { ...defaults.action_costs, ...(src.action_costs || {}) },
    copilot: { confirm_threshold_messages: src.copilot?.confirm_threshold_messages ?? 2, bands: Array.isArray(src.copilot?.bands) ? src.copilot.bands : [] },
    iap_message_quantities: src.iap_message_quantities || {},
    conversion_rate: src.conversion_rate == null ? '' : String(src.conversion_rate),
  };
}

export function economyPayload(economy) {
  const bands = (economy.copilot.bands || []).map((row, index) => ({
    min_usd: Number(row.min_usd ?? 0),
    max_usd: row.max_usd === '' || row.max_usd == null ? undefined : Number(row.max_usd),
    message_units: Number(row.message_units || 1),
    enabled: row.enabled !== false,
    order: index,
  }));
  const iap = {};
  for (const [productId, qty] of Object.entries(economy.iap_message_quantities || {})) {
    if (String(productId).trim() && Number(qty) > 0) iap[String(productId).trim()] = Number(qty);
  }
  return {
    action_costs: {
      ai_dm_reply: Number(economy.action_costs.ai_dm_reply),
      ai_web_chat: Number(economy.action_costs.ai_web_chat),
      ai_whatsapp: Number(economy.action_costs.ai_whatsapp),
      ai_tiktok: Number(economy.action_costs.ai_tiktok),
      ai_public_comment: Number(economy.action_costs.ai_public_comment),
      ai_comment_dm: Number(economy.action_costs.ai_comment_dm),
      ai_both_mode: String(economy.action_costs.ai_both_mode || 'each'),
      followup_sent: Number(economy.action_costs.followup_sent),
    },
    copilot: { confirm_threshold_messages: Number(economy.copilot.confirm_threshold_messages), bands },
    iap_message_quantities: iap,
    conversion_rate: String(economy.conversion_rate || '').trim() ? Number(economy.conversion_rate) : null,
  };
}

const ACTIONS = ['ai_dm_reply', 'ai_web_chat', 'ai_whatsapp', 'ai_tiktok', 'ai_public_comment', 'ai_comment_dm', 'followup_sent'];

export default function OwnerEconomy({ embedded = false }) {
  const [catalog, setCatalog] = useState(/** @type {any} */ (null));
  const [economy, setEconomy] = useState(emptyEconomy());
  const [error, setError] = useState('');
  const [dirty, setDirty] = useState(false);
  const [dryRun, setDryRun] = useState(/** @type {any} */ (null));
  useEffect(() => {
    if (!dirty) return undefined;
    const warn = (event) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);
  useEffect(() => {
    let live = true;
    ownerApi.messageCatalog().then((data) => { if (!live) return; setCatalog(data.catalog); setEconomy(economyFromCatalog(data.catalog)); }).catch((reason) => live && setError(reason.message));
    return () => { live = false; };
  }, []);
  async function save() {
    const data = await ownerApi.updateMessageCatalog({ economy: economyPayload(economy), reason: 'economy_edit' });
    setCatalog(data.catalog);
    setEconomy(economyFromCatalog(data.catalog));
    setDirty(false);
  }
  return (
    <div className="space-y-6">
      {embedded ? null : <PageHeader title="Message pricing" subtitle="How many messages each AI action takes from a business's balance." />}
      {error ? <Alert title="We couldn't save pricing." detail={error} /> : null}
      <Card title="Messages charged per AI action">
        {ACTIONS.map((key) => (
          <label key={key} className="mt-3 flex max-w-xl items-center gap-3 text-sm">
            <span>{label('actionCost', key)}</span>
            <input aria-label={label('actionCost', key)} className="h-9 w-24 rounded-lg border border-[#7C8798] px-3 text-right tabular-nums" value={economy.action_costs[key]} onChange={(event) => { setDirty(true); setEconomy((current) => ({ ...current, action_costs: { ...current.action_costs, [key]: event.target.value } })); }} />
            <span>messages</span>
          </label>
        ))}
        <label className="mt-4 block text-sm">When the AI replies to a comment and also sends a DM
          <select className="mt-1 h-9 w-full rounded-lg border border-[#7C8798] px-3" value={economy.action_costs.ai_both_mode} onChange={(event) => { setDirty(true); setEconomy((current) => ({ ...current, action_costs: { ...current.action_costs, ai_both_mode: event.target.value } })); }}>
            <option value="each">Charge for both</option>
            <option value="once">Charge once (the higher of the two)</option>
          </select>
        </label>
      </Card>
      <Card title="Old credits to messages">
        <label className="block text-sm">How many messages is 1 old credit worth?
          <input className="mt-1 h-9 w-full rounded-lg border border-[#7C8798] px-3" value={economy.conversion_rate} onChange={(event) => { setDirty(true); setEconomy((current) => ({ ...current, conversion_rate: event.target.value })); }} />
        </label>
        <p className="mt-1 text-sm text-slate-600">Leave blank until you decide. Old credits stay as they are until this is set.</p>
        <Button variant="secondary" onClick={() => { void ownerApi.conversionDryRun().then((data) => setDryRun(data.dry_run)).catch((reason) => setError(reason.message)); }}>Preview conversion</Button>
        {dryRun ? <TechDetails text={JSON.stringify(dryRun, null, 2)} /> : null}
      </Card>
      <div className="flex gap-3">
        <Button onClick={() => { void save().catch((reason) => setError(reason.message)); }}>Save changes</Button>
        <Button variant="secondary" onClick={() => { setEconomy(economyFromCatalog(catalog)); setDirty(false); }}>Discard</Button>
      </div>
    </div>
  );
}
