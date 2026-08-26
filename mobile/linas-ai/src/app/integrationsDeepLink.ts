import type { StringKey } from '../i18n/locales/en';

export type IntegrationsDeepLink = {
  metaConnection: 'success' | 'cancelled' | 'failed' | null;
  waConnection: 'success' | 'cancelled' | 'failed' | null;
  waError: string | null;
  metaReason: string | null;
  metaChannel: 'facebook' | 'instagram' | null;
};

const WA_ERRORS = new Set([
  'coexistence_flow_required',
  'meta_advanced_access_required',
  'session_timeout',
  'embedded_signup_timeout',
  'session_version_invalid',
  'coexistence_not_proven',
  'coexistence_phone_ambiguous',
]);

const META_REASONS = new Set([
  'generic',
  'state',
  'scopes',
  'token',
  'profile',
  'webhook',
  'deletion',
  'deletion_failed',
  'busy',
  'guard',
  'conflict',
  'config',
  'no_page',
  'provider',
  'rate_limit',
]);

export function parseMetaOAuthFailureReason(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const normalized = value.trim().toLowerCase();
  return META_REASONS.has(normalized) ? normalized : null;
}

/** Read only the server's allowlisted enum; never surface arbitrary API text. */
export function metaOAuthFailureReasonFromApiBody(body: unknown): string | null {
  if (!body || typeof body !== 'object' || Array.isArray(body)) return null;
  const detail = (body as { detail?: unknown }).detail;
  if (!detail || typeof detail !== 'object' || Array.isArray(detail)) return null;
  return parseMetaOAuthFailureReason((detail as { meta_reason?: unknown }).meta_reason);
}

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
    const rawWaError = (parsed.searchParams.get('wa_error') || '').trim().toLowerCase();
    const rawChannel = (parsed.searchParams.get('channel') || '').trim().toLowerCase();
    let metaConnection: IntegrationsDeepLink['metaConnection'] = null;
    if (rawMeta === 'success' || rawMeta === 'connected') metaConnection = 'success';
    else if (rawMeta === 'cancelled' || rawMeta === 'canceled') metaConnection = 'cancelled';
    else if (rawMeta === 'failed') metaConnection = 'failed';
    let waConnection: IntegrationsDeepLink['waConnection'] = null;
    if (rawWa === 'success' || rawWa === 'connected') waConnection = 'success';
    else if (rawWa === 'cancelled' || rawWa === 'canceled') waConnection = 'cancelled';
    else if (rawWa === 'failed') waConnection = 'failed';
    const metaReason = parseMetaOAuthFailureReason(rawReason);
    const waError = WA_ERRORS.has(rawWaError) ? rawWaError : null;
    const metaChannel = rawChannel === 'facebook' || rawChannel === 'instagram' ? rawChannel : null;
    return { metaConnection, waConnection, waError, metaReason, metaChannel };
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

export function metaOAuthFailureMessage(
  tr: (key: StringKey) => string,
  reason: string | null,
  channel: 'facebook' | 'instagram' | null = null,
): string {
  if (channel === 'facebook') {
    switch (reason) {
      case 'scopes':
        return tr('metaOAuthFailedFacebookScopes');
      case 'token':
        return tr('metaOAuthFailedFacebookToken');
      case 'webhook':
        return tr('metaOAuthFailedFacebookWebhook');
      case 'deletion':
        return tr('metaOAuthFailedFacebookDeletion');
      case 'deletion_failed':
        return tr('metaOAuthFailedFacebookDeletionFailed');
      case 'busy':
        return tr('metaOAuthFailedFacebookBusy');
      case 'guard':
        return tr('metaOAuthFailedFacebookGuard');
      case 'config':
        return tr('metaOAuthFailedFacebookConfig');
      case 'conflict':
        return tr('metaOAuthFailedFacebookConflict');
      case 'no_page':
        return tr('metaOAuthFailedFacebookNoPage');
      default:
        return tr('metaOAuthFailedFacebook');
    }
  }
  if (channel !== 'instagram') {
    return tr('metaOAuthFailed');
  }
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
    case 'deletion_failed':
      return tr('metaOAuthFailedDeletionFailed');
    case 'busy':
      return tr('metaOAuthFailedBusy');
    case 'guard':
      return tr('metaOAuthFailedGuard');
    case 'config':
      return tr('metaOAuthFailedConfig');
    case 'conflict':
      return tr('metaOAuthFailedConflict');
    case 'provider':
      return tr('metaOAuthFailedProvider');
    case 'rate_limit':
      return tr('metaOAuthFailedRateLimit');
    default:
      return tr('metaOAuthFailed');
  }
}
