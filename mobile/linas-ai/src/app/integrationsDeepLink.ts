export type IntegrationsDeepLink = {
  metaConnection: 'success' | 'cancelled' | 'failed' | null;
  waConnection: 'success' | 'cancelled' | 'failed' | null;
};

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
    let metaConnection: IntegrationsDeepLink['metaConnection'] = null;
    if (rawMeta === 'success' || rawMeta === 'connected') metaConnection = 'success';
    else if (rawMeta === 'cancelled' || rawMeta === 'canceled') metaConnection = 'cancelled';
    else if (rawMeta === 'failed') metaConnection = 'failed';
    let waConnection: IntegrationsDeepLink['waConnection'] = null;
    if (rawWa === 'success' || rawWa === 'connected') waConnection = 'success';
    else if (rawWa === 'cancelled' || rawWa === 'canceled') waConnection = 'cancelled';
    else if (rawWa === 'failed') waConnection = 'failed';
    return { metaConnection, waConnection };
  } catch {
    return null;
  }
}

export type MetaAuthSessionOutcome = 'ok' | 'cancelled' | 'failed' | 'incomplete';

/** iOS often ends the session on facebook.com / HTTPS before linasai:// arrives. */
export function metaAuthSessionOutcome(result: {
  type: string;
  url?: string | null;
}): MetaAuthSessionOutcome {
  if (result.type === 'cancel' || result.type === 'dismiss') return 'cancelled';
  if (result.type !== 'success') return 'incomplete';
  const parsed = parseIntegrationsDeepLink(result.url ?? null);
  if (parsed?.metaConnection === 'success') return 'ok';
  if (parsed?.metaConnection === 'cancelled') return 'cancelled';
  if (parsed?.metaConnection === 'failed') return 'failed';
  return 'incomplete';
}
