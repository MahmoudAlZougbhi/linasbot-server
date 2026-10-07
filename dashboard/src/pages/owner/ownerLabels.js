/** @type {Record<string, string>} */
export const READINESS_LABELS = {
  free_ai_message_allowance: 'Free message allowance',
  free_message_renewal: 'Free message renewal',
  knowledge_line_budget: 'Knowledge line budget',
  services_products_line_budget: 'Services and products budget',
  content_line_definition: 'Content line definition',
  message_topup_prices: 'Top-up prices',
  credit_to_message_conversion: 'Credit conversion',
  alembic_head: 'Database migrations',
  message_catalog_unpublished: 'Message catalog publish',
  message_checkout_not_ready: 'Checkout',
  message_topup_not_sale_ready: 'Top-up sales',
  message_billing_cutover_off: 'Billing cutover',
  live_message_ready: 'Live messages',
  live_message_skus_not_sale_ready: 'Live message prices are not ready to sell',
  eval_suite_below_800: 'Eval suite',
  live_channel_proof_missing: 'Live channel proof',
  live_voyage_pgvector_unverified: 'Search index',
  unresolved_pending_settlements: 'Pending settlements',
  stale_leftover_credit_holds: 'Leftover credit holds',
};

/** @type {Record<string, string>} */
export const PAYMENT_LABELS = {
  incomplete: 'Incomplete',
  ok: 'Ready',
  unconfigured: 'Not configured',
  google_iap_not_fully_implemented: 'Google Play billing is not finished',
};

/** @param {string} key */
export function readinessLabel(key) {
  return READINESS_LABELS[key] || String(key || '').replaceAll('_', ' ');
}

/** @param {string} key */
export function paymentLabel(key) {
  if (key == null || key === '') return 'Not configured';
  const value = String(key);
  return PAYMENT_LABELS[value] || value.replaceAll('_', ' ');
}
