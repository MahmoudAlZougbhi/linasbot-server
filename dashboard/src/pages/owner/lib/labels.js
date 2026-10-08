// @ts-nocheck
const ACRONYMS = new Set(['ai', 'dm', 'faq', 'usd', 'id', 'api', 'sms']);
const BRANDS = {
  whatsapp: 'WhatsApp',
  tiktok: 'TikTok',
  instagram: 'Instagram',
  facebook: 'Facebook',
  messenger: 'Messenger',
  openai: 'OpenAI',
  stripe: 'Stripe',
};

/** @param {string} key */
export function humanize(key) {
  const words = String(key || '').replace(/[_-]+/g, ' ').trim().split(/\s+/).filter(Boolean);
  return words.map((word, index) => {
    const lower = word.toLowerCase();
    if (lower === 'qa') return index === 0 ? 'Answer' : 'answer';
    if (lower === 'kb') return index === 0 ? 'Knowledge' : 'knowledge';
    if (ACRONYMS.has(lower)) return lower.toUpperCase();
    if (BRANDS[lower]) return BRANDS[lower];
    if (index === 0) return lower.charAt(0).toUpperCase() + lower.slice(1);
    return lower;
  }).join(' ');
}

/** @type {Record<string, Record<string, string>>} */
export const MAPS = {
  channel: {
    instagram_dm: 'Instagram DM',
    instagram_comment: 'Instagram comment',
    instagram: 'Instagram',
    facebook_comment: 'Facebook comment',
    facebook: 'Facebook Messenger',
    messenger: 'Facebook Messenger',
    facebook_dm: 'Facebook Messenger',
    tiktok: 'TikTok',
    tiktok_comment: 'TikTok comment',
    whatsapp: 'WhatsApp',
    web: 'Website chat',
    web_chat: 'Website chat',
    brains_test: 'Test chat',
    unknown: 'Other',
    '': 'Other',
  },
  brain: { customer: 'Customer AI', owner_copilot: 'Owner Copilot', copilot: 'Owner Copilot' },
  role: { platform_owner: 'Platform owner', owner: 'Owner', admin: 'Admin', operator: 'Operator', viewer: 'Viewer' },
  plan: { lite: 'Lite', starter: 'Starter', growth: 'Growth', pro: 'Pro', max: 'Max', none: 'No plan', '': 'No plan' },
  membership: { active: 'Active', none: 'No subscription', past_due: 'Payment overdue', canceled: 'Cancelled', trialing: 'Trial' },
  language: { en: 'English', ar: 'Arabic', fr: 'French', franco: 'Franco (Arabic in Latin letters)' },
  languageChip: { en: 'EN', ar: 'AR', fr: 'FR', franco: 'Franco' },
  responseClass: { generated_ai: 'AI-written reply', faq: 'Ready answer', faq_static: 'Ready answer', static: 'Ready answer', followup: 'Follow-up' },
  evidenceFamily: { hours: 'Opening hours', branches: 'Branches', knowledge: 'Knowledge', services: 'Services', products: 'Products', faq: 'Ready answers', offers: 'Offers' },
  traceStep: { receive: 'Received', faq_or_retrieve: 'Checked ready answers & knowledge', reply: 'Replied', lab: 'Test chat' },
  costCategory: { llm_generation: 'AI replies', embedding: 'Search indexing', rerank: 'Search ranking', visual: 'Image & video understanding', transcription: 'Voice notes' },
  provider: { openai: 'OpenAI', voyage: 'Voyage AI', anthropic: 'Anthropic', google: 'Google' },
  auditAction: {
    brain_lab_customer: 'Tested Customer AI',
    brain_lab_copilot: 'Tested Owner Copilot',
    suspend: 'Suspended business',
    unsuspend: 'Restored business',
    reactivate: 'Restored business',
    user_update: 'Updated user',
    update_user: 'Updated user',
    tenant_visibility: 'Changed business visibility',
    publish: 'Published plans & prices',
    portal_edit: 'Edited plans & prices',
    economy_edit: 'Edited message pricing',
    copilot_qa_save: 'Added Copilot answer',
    copilot_qa_delete: 'Deleted Copilot answer',
    copilot_kb_save: 'Added Copilot knowledge',
    copilot_kb_delete: 'Deleted Copilot knowledge',
  },
  freeField: { free_ai_message_allowance: 'Free messages per month', included_messages: 'Free messages per month', free_message_renewal: 'How free messages renew', knowledge_line_budget: 'Knowledge lines allowed', services_products_line_budget: 'Services & products lines allowed', content_line_definition: 'What counts as one line', message_topup_prices: 'Top-up prices', credit_to_message_conversion: 'Old credits → messages conversion' },
  actionCost: { ai_dm_reply: 'Instagram & Facebook DM reply', ai_web_chat: 'Website chat reply', ai_whatsapp: 'WhatsApp reply', ai_tiktok: 'TikTok reply', ai_public_comment: 'Public comment reply', ai_comment_dm: 'DM sent after a comment', followup_sent: 'Smart follow-up' },
  range: { last_day: 'Last 24 hours', last_7_days: 'Last 7 days', last_week: 'Since Monday last week', last_month: 'Last 30 days', last_6_months: 'Last 6 months', last_year: 'Last 12 months' },
  costPeriod: { '': 'All time', today: 'Today', yesterday: 'Yesterday', last_7_days: 'Last 7 days', last_30_days: 'Last 30 days' },
};

export const READINESS = {
  free_ai_message_allowance: { label: 'Free messages per month', group: 'Pricing decisions', text: 'Set how many free messages a new business gets.' },
  free_message_renewal: { label: 'How free messages renew', group: 'Pricing decisions', text: 'Choose how the free allowance renews.' },
  knowledge_line_budget: { label: 'Knowledge lines allowed', group: 'Pricing decisions', text: 'Set the knowledge line limit.' },
  services_products_line_budget: { label: 'Services & products lines allowed', group: 'Pricing decisions', text: 'Set the services and products line limit.' },
  content_line_definition: { label: 'What counts as one line', group: 'Pricing decisions', text: 'Describe what counts as one content line.' },
  message_topup_prices: { label: 'Top-up prices', group: 'Pricing decisions', text: 'Set prices for extra message packs.' },
  credit_to_message_conversion: { label: 'Old credits conversion', group: 'Pricing decisions', text: 'Decide how old credits become messages.' },
  message_catalog_unpublished: { label: 'Prices published', group: 'Store & checkout', text: 'Publish your plans and prices.' },
  message_checkout_not_ready: { label: 'Checkout ready', group: 'Store & checkout', text: 'Finish checkout for message plans.' },
  message_topup_not_sale_ready: { label: 'Top-up packs for sale', group: 'Store & checkout', text: 'Make top-up packs ready to sell.' },
  live_message_skus_not_sale_ready: { label: 'Live message prices ready to sell', group: 'Store & checkout', text: 'Live message prices are not ready to sell.' },
  live_message_ready: { label: 'Live message prices', group: 'Store & checkout', text: 'Confirm live message prices.' },
  message_billing_cutover_off: { label: 'Switch to message billing', group: 'Store & checkout', text: 'Turn on message billing.' },
  eval_suite_below_800: { label: 'AI quality test score', group: 'Quality checks', text: 'AI quality test score is below target.' },
  live_channel_proof_missing: { label: 'Real channel test', group: 'Quality checks', text: 'Confirm a real Instagram or Facebook message works end to end.' },
  live_voyage_pgvector_unverified: { label: 'Search index check', group: 'Quality checks', text: 'Confirm knowledge search works in production.' },
  alembic_head: { label: 'Database up to date', group: 'Quality checks', text: 'The database needs its latest update.' },
  unresolved_pending_settlements: { label: 'Charges waiting for review', group: 'Clean-up', text: 'Review charges that are still waiting.' },
  stale_leftover_credit_holds: { label: 'Old credit holds to release', group: 'Clean-up', text: 'Release old credit holds.' },
};

/** @param {string} kind @param {string} key */
export function label(kind, key) {
  const map = MAPS[kind] || {};
  const value = key == null ? '' : String(key);
  if (Object.prototype.hasOwnProperty.call(map, value)) return map[value];
  if (!value) return 'Other';
  return humanize(value);
}

/** @param {string} message */
export function errorLabel(message) {
  const text = String(message || '');
  if (/unknown tenant/i.test(text)) return "We couldn't find that business.";
  if (/message_flow_not_found/i.test(text)) return 'This message is no longer available.';
  if (/free_offer_unconfigured/i.test(text)) return 'Fill in the free plan first (see the list above).';
  if (/401/.test(text)) return 'Your session ended. Please sign in again.';
  if (!text) return 'Something went wrong. Please try again.';
  if (/_/.test(text)) return 'Something went wrong. Please try again.';
  return text;
}
