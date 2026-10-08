// @ts-nocheck
export function parseOptionalInt(raw, label) {
  const text = String(raw ?? '').trim();
  if (!text) return undefined;
  if (!/^-?\d+$/.test(text)) throw new Error(`${label} must be an integer`);
  return Number(text);
}

export function planDraftFromCatalog(catalog) {
  /** @type {Record<string, any>} */
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

const FREE_NOTE_FIELDS = [
  'free_message_renewal',
  'knowledge_line_budget',
  'services_products_line_budget',
  'content_line_definition',
  'message_topup_prices',
  'credit_to_message_conversion',
];

export function freeDraftFromCatalog(catalog) {
  const free = catalog?.free || {};
  const src = free.configured && typeof free.configured === 'object' ? free.configured : {};
  /** @type {Record<string, string>} */
  const configured = {};
  for (const field of FREE_NOTE_FIELDS) configured[field] = src[field] == null ? '' : String(src[field]);
  return { included_messages: free.included_messages == null ? '' : String(free.included_messages), configured };
}

export { FREE_NOTE_FIELDS };
