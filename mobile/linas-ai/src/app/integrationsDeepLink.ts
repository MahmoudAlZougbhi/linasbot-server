import type { StringKey } from '../i18n/locales/en';

export type IntegrationsDeepLink = {
  metaConnection: 'success' | 'cancelled' | 'failed' | null;
  waConnection: 'success' | 'cancelled' | 'failed' | null;
  metaReason: string | null;
};

const META_REASONS = new Set([
  'generic',
  'state',
  'scopes',
  'token',
  'profile',
  'webhook',
  'deletion',
  'conflict',
  'config',
]);

export function parseIntegrationsDeepLink(url: string | null): IntegrationsDeepLink | null {
  if (!url) return null;
  try {
    const normalized = url.replace(/^linasai:\/\//i, 'https://linasai.app/');
    const parsed = new URL(normalized);
    const path = parsed.pathname.replace(/^\//, '');
    // Exact OAuth return path only — never bridge URLs like integrations/whatsapp/...
    if (path !== 'integrations') {
      return null;
    }
    const rawMeta = (parsed.searchParams.get('meta_connection') || '').trim().toLowerCase();
    const rawWa = (parsed.searchParams.get('wa_connection') || '').trim().toLowerCase();
    const rawReason = (parsed.searchParams.get('meta_reason') || '').trim().toLowerCase();
    let metaConnection: IntegrationsDeepLink['metaConnection'] = null;
    if (rawMeta === 'success' || rawMeta === 'connected') metaConnection = 'success';
    else if (rawMeta === 'cancelled' || rawMeta === 'canceled') metaConnection = 'cancelled';
    else if (rawMeta === 'failed') metaConnection = 'failed';
    let waConnection: IntegrationsDeepLink['waConnection'] = null;
    if (rawWa === 'success' || rawWa === 'connected') waConnection = 'success';
    else if (rawWa === 'cancelled' || rawWa === 'canceled') waConnection = 'cancelled';
    else if (rawWa === 'failed') waConnection = 'failed';
    const metaReason = META_REASONS.has(rawReason) ? rawReason : null;
    return { metaConnection, waConnection, metaReason };
  } catch {
    return null;
  }
}

export type MetaAuthSessionOutcome = 'ok' | 'cancelled' | 'failed' | 'incomplete';

export type MetaAuthSessionResult = {
  outcome: MetaAuthSessionOutcome;
  reason: string | null;
};

/** iOS often ends the session on facebook.com / HTTPS before linasai:// arrives. */
export function metaAuthSessionOutcome(result: {
  type: string;
  url?: string | null;
}): MetaAuthSessionResult {
  if (result.type === 'cancel' || result.type === 'dismiss') {
    return { outcome: 'cancelled', reason: null };
  }
  if (result.type !== 'success') {
    return { outcome: 'incomplete', reason: null };
  }
  const parsed = parseIntegrationsDeepLink(result.url ?? null);
  if (parsed?.metaConnection === 'success') return { outcome: 'ok', reason: null };
  if (parsed?.metaConnection === 'cancelled') return { outcome: 'cancelled', reason: null };
  if (parsed?.metaConnection === 'failed') {
    return { outcome: 'failed', reason: parsed.metaReason };
  }
  return { outcome: 'incomplete', reason: null };
}

export function metaOAuthFailureMessage(tr: (key: StringKey) => string, reason: string | null): string {
  switch (reason) {
    case 'scopes':
      return tr('metaOAuthFailedScopes');
    case 'token':
      return tr('metaOAuthFailedToken');
    case 'profile':
      return tr('metaOAuthFailedProfile');
    case 'webhook':
      return tr('metaOAuthFailedWebhook');
    case 'deletion':
      return tr('metaOAuthFailedDeletion');
    case 'config':
      return tr('metaOAuthFailedConfig');
    case 'conflict':
      return tr('metaOAuthFailedConflict');
    default:
      return tr('metaOAuthFailed');
  }
}
