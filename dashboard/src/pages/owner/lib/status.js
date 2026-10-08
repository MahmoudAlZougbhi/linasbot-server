// @ts-nocheck
/** @typedef {'success'|'warning'|'danger'|'info'|'neutral'} Tone */

/** @param {string} kind @param {unknown} value @returns {Tone} */
export function statusTone(kind, value) {
  const text = String(value ?? '');
  if (kind === 'message' && text === 'sent') return 'success';
  if (kind === 'message' && text === 'failed') return 'danger';
  if (kind === 'message' && (text === 'accepted' || text === 'pending_settlement')) return 'warning';
  if (kind === 'trace') return value ? 'danger' : 'success';
  if (kind === 'user' && text === 'blocked') return 'danger';
  if (kind === 'user' && text === 'test') return 'info';
  if (kind === 'user') return 'success';
  if (kind === 'planLive') return value ? 'success' : 'neutral';
  if (kind === 'published') return value ? 'success' : 'warning';
  if (kind === 'cost') return value ? 'success' : 'warning';
  if (kind === 'health') return value ? 'success' : 'danger';
  if (kind === 'payment' && (text === 'implemented' || text === 'ok')) return 'success';
  if (kind === 'payment' && text === 'incomplete') return 'warning';
  return 'neutral';
}

/** @param {string} kind @param {unknown} value */
export function statusLabel(kind, value) {
  const text = String(value ?? '');
  if (kind === 'message' && text === 'sent') return 'Sent';
  if (kind === 'message' && text === 'failed') return 'Failed';
  if (kind === 'message' && text === 'accepted') return 'In progress';
  if (kind === 'message' && text === 'pending_settlement') return 'Waiting for billing';
  if (kind === 'trace') return value ? 'Error' : 'OK';
  if (kind === 'user' && text === 'blocked') return 'Blocked';
  if (kind === 'user' && text === 'test') return 'Test account';
  if (kind === 'user') return 'Active';
  if (kind === 'membership' && text === 'none') return 'No plan';
  if (kind === 'planLive') return value ? 'Live' : 'Not live yet';
  if (kind === 'sale') return value ? 'For sale' : 'Not for sale yet';
  if (kind === 'published') return value ? 'Published' : 'Draft';
  if (kind === 'cost') return value ? 'Priced' : 'Not priced yet';
  if (kind === 'health') return value ? 'Working' : 'Not reachable';
  if (kind === 'payment' && (text === 'implemented' || text === 'ok')) return 'Ready';
  if (kind === 'payment' && text === 'incomplete') return 'Not finished';
  if (kind === 'payment' && text === 'retired_token_packs') return 'Not used';
  if (kind === 'payment') return 'Not set up';
  return 'Not set';
}
