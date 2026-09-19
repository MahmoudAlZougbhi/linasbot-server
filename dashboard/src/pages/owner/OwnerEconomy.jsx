import { useEffect, useState } from 'react';
import { ownerApi } from './ownerApi';

/** @returns {any} */
function emptyEconomy() {
  return {
    action_costs: {
      ai_dm_reply: 1,
      ai_web_chat: 1,
      ai_whatsapp: 1,
      ai_tiktok: 1,
      ai_public_comment: 1,
      ai_comment_dm: 1,
      ai_both_mode: 'each',
      followup_sent: 1,
    },
    copilot: { confirm_threshold_messages: 2, bands: [] },
    iap_message_quantities: {},
    conversion_rate: '',
  };
}

/** @param {any} catalog @returns {any} */
function economyFromCatalog(catalog) {
  const src = catalog?.economy && typeof catalog.economy === 'object' ? catalog.economy : {};
  const defaults = emptyEconomy();
  return {
    action_costs: { ...defaults.action_costs, ...(src.action_costs || {}) },
    copilot: {
      confirm_threshold_messages: src.copilot?.confirm_threshold_messages ?? 2,
      bands: Array.isArray(src.copilot?.bands) ? src.copilot.bands : [],
    },
    iap_message_quantities: src.iap_message_quantities || {},
    conversion_rate: src.conversion_rate == null ? '' : String(src.conversion_rate),
  };
}

export default function OwnerEconomy() {
  const [catalog, setCatalog] = useState(/** @type {any} */ (null));
  const [economy, setEconomy] = useState(/** @type {any} */ (emptyEconomy()));
  const [error, setError] = useState('');
  const [dryRun, setDryRun] = useState(/** @type {any} */ (null));

  useEffect(() => {
    let live = true;
    ownerApi
      .messageCatalog()
      .then((data) => {
        if (!live) return;
        setCatalog(data.catalog);
        setEconomy(economyFromCatalog(data.catalog));
      })
      .catch((reason) => live && setError(reason.message));
    return () => {
      live = false;
    };
  }, []);

  /** @param {string} key @param {string} value */
  function editCost(key, value) {
    setEconomy((/** @type {any} */ current) => ({
      ...current,
      action_costs: { ...current.action_costs, [key]: value },
    }));
  }

  async function save() {
    setError('');
    try {
      const bands = (economy.copilot.bands || []).map((/** @type {any} */ row, /** @type {number} */ index) => ({
        min_usd: Number(row.min_usd ?? 0),
        max_usd: row.max_usd === '' || row.max_usd == null ? undefined : Number(row.max_usd),
        message_units: Number(row.message_units || 1),
        enabled: row.enabled !== false,
        order: index,
      }));
      /** @type {Record<string, number>} */
      const iap = {};
      for (const [productId, qty] of Object.entries(economy.iap_message_quantities || {})) {
        if (String(productId).trim() && Number(qty) > 0) iap[String(productId).trim()] = Number(qty);
      }
      const payload = {
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
        copilot: {
          confirm_threshold_messages: Number(economy.copilot.confirm_threshold_messages),
          bands,
        },
        iap_message_quantities: iap,
        conversion_rate: String(economy.conversion_rate || '').trim()
          ? Number(economy.conversion_rate)
          : null,
      };
      const data = await ownerApi.updateMessageCatalog({ economy: payload, reason: 'economy_edit' });
      setCatalog(data.catalog);
      setEconomy(economyFromCatalog(data.catalog));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }

  async function runDryRun() {
    setError('');
    try {
      const data = await ownerApi.conversionDryRun();
      setDryRun(data.dry_run);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }

  function addBand() {
    setEconomy((/** @type {any} */ current) => ({
      ...current,
      copilot: {
        ...current.copilot,
        bands: [...(current.copilot.bands || []), { min_usd: '', max_usd: '', message_units: 1 }],
      },
    }));
  }

  const costs = economy.action_costs;
  return (
    <div className="space-y-7">
      <header>
        <h2 className="text-2xl font-semibold">Message economy</h2>
        <p className="mt-1 text-sm text-slate-400">
          Action costs, Owner Copilot cost bands, extra-message pack map, and conversion policy.
          Historical credit ledgers stay read-only until a conversion rate is approved.
        </p>
      </header>
      {error && (
        <p role="alert" className="rounded-lg bg-red-950 p-3 text-sm text-red-200">
          {error}
        </p>
      )}
      <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
        <h3 className="text-lg font-medium">Customer AI action costs</h3>
        {[
          ['ai_dm_reply', 'Instagram / Facebook AI DM'],
          ['ai_web_chat', 'Web Chat AI'],
          ['ai_whatsapp', 'WhatsApp AI'],
          ['ai_tiktok', 'TikTok AI'],
          ['ai_public_comment', 'AI public comment'],
          ['ai_comment_dm', 'Comment-generated DM'],
          ['followup_sent', 'Smart follow-up'],
        ].map(([key, label]) => (
          <label key={key} className="mt-3 block text-sm text-slate-300">
            {label}
            <input
              className="mt-1 block rounded-lg border border-slate-700 bg-slate-950 px-3 py-2"
              value={costs[/** @type {string} */ (key)]}
              onChange={(event) => editCost(/** @type {string} */ (key), event.target.value)}
            />
          </label>
        ))}
        <label className="mt-3 block text-sm text-slate-300">
          Both comment + DM
          <select
            className="mt-1 block rounded-lg border border-slate-700 bg-slate-950 px-3 py-2"
            value={costs.ai_both_mode}
            onChange={(event) => editCost('ai_both_mode', event.target.value)}
          >
            <option value="each">Charge each action</option>
            <option value="once">Charge once (max of the two)</option>
          </select>
        </label>
      </section>
      <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
        <h3 className="text-lg font-medium">Owner Copilot bands</h3>
        <label className="mt-3 block text-sm text-slate-300">
          Confirmation threshold (messages)
          <input
            className="mt-1 block rounded-lg border border-slate-700 bg-slate-950 px-3 py-2"
            value={economy.copilot.confirm_threshold_messages}
            onChange={(event) =>
              setEconomy((/** @type {any} */ current) => ({
                ...current,
                copilot: { ...current.copilot, confirm_threshold_messages: event.target.value },
              }))
            }
          />
        </label>
        {(economy.copilot.bands || []).map((/** @type {any} */ band, /** @type {number} */ index) => (
          <div key={index} className="mt-3 grid gap-2 md:grid-cols-3">
            <input
              className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2"
              placeholder="min USD"
              value={band.min_usd ?? ''}
              onChange={(event) => {
                const next = [...economy.copilot.bands];
                next[index] = { ...next[index], min_usd: event.target.value };
                setEconomy((/** @type {any} */ current) => ({ ...current, copilot: { ...current.copilot, bands: next } }));
              }}
            />
            <input
              className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2"
              placeholder="max USD"
              value={band.max_usd ?? ''}
              onChange={(event) => {
                const next = [...economy.copilot.bands];
                next[index] = { ...next[index], max_usd: event.target.value };
                setEconomy((/** @type {any} */ current) => ({ ...current, copilot: { ...current.copilot, bands: next } }));
              }}
            />
            <input
              className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2"
              placeholder="messages"
              value={band.message_units ?? ''}
              onChange={(event) => {
                const next = [...economy.copilot.bands];
                next[index] = { ...next[index], message_units: event.target.value };
                setEconomy((/** @type {any} */ current) => ({ ...current, copilot: { ...current.copilot, bands: next } }));
              }}
            />
          </div>
        ))}
        <button type="button" onClick={addBand} className="mt-3 rounded border border-slate-600 px-3 py-2">
          Add band
        </button>
      </section>
      <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
        <h3 className="text-lg font-medium">Approved conversion rate</h3>
        <p className="mt-1 text-sm text-slate-400">
          Leave blank to keep historical credits unconverted. Do not guess 1:1.
        </p>
        <input
          className="mt-3 block rounded-lg border border-slate-700 bg-slate-950 px-3 py-2"
          value={economy.conversion_rate}
          onChange={(event) => setEconomy((/** @type {any} */ current) => ({ ...current, conversion_rate: event.target.value }))}
        />
        <button type="button" onClick={() => void runDryRun()} className="mt-3 rounded border border-slate-600 px-3 py-2">
          Dry-run inventory
        </button>
        {dryRun && (
          <pre className="mt-3 overflow-auto rounded bg-slate-950 p-3 text-xs text-slate-300">
            {JSON.stringify(dryRun, null, 2)}
          </pre>
        )}
      </section>
      <button type="button" onClick={() => void save()} className="rounded bg-teal-500 px-3 py-2 text-slate-950">
        Save economy
      </button>
      <p className="text-xs text-slate-500">Catalog revision {catalog?.admin_revision || '—'}</p>
    </div>
  );
}
