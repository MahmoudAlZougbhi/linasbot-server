import type { MetaAuthSessionOutcome } from '../../app/integrationsDeepLink';
import type { IntegrationListRow } from './integrationsSchemas';
import type { IntegrationsLoadResult } from './useIntegrationsLoad';

/**
 * Instagram Login on a first-time Safari login often lands on the IG account
 * page when force_reauth is already on. First attempt strips it; retry puts it back.
 */
export function withInstagramMobileReauth(url: string, forceReauth = true): string {
  const parsed = new URL(url);
  if (parsed.hostname !== 'www.instagram.com') return url;
  if (forceReauth) parsed.searchParams.set('force_reauth', 'true');
  else parsed.searchParams.delete('force_reauth');
  return parsed.toString();
}

/** Facebook Login usually lands before the auth sheet closes. */
export const META_CONNECT_POLL_DELAYS_MS = [600, 1200] as const;

/**
 * First Instagram Login often finishes after Safari closes on the account page.
 * Keep polling long enough for the callback to persist before a force_reauth retry.
 */
export const INSTAGRAM_CONNECT_POLL_DELAYS_MS = [1000, 2000, 3000, 4000] as const;

export const INSTAGRAM_CONNECT_RETRY_PAUSE_MS = 800;

export function connectPollDelaysMs(platform: 'instagram' | 'facebook'): readonly number[] {
  return platform === 'instagram' ? INSTAGRAM_CONNECT_POLL_DELAYS_MS : META_CONNECT_POLL_DELAYS_MS;
}

export function findIntegrationRow(rows: IntegrationListRow[], platform: string) {
  return rows.find((item) => item.platform === platform);
}

export function shouldRetryInstagramConnect(
  platform: 'instagram' | 'facebook',
  outcome: MetaAuthSessionOutcome,
  connected: boolean,
): boolean {
  if (platform !== 'instagram' || connected) return false;
  return outcome === 'cancelled' || outcome === 'incomplete';
}

export function sleepMs(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function resolveConnectedRow(
  load: () => Promise<IntegrationsLoadResult>,
  platform: string,
  delays: readonly number[] = META_CONNECT_POLL_DELAYS_MS,
): Promise<{ ok: false } | { ok: true; row: IntegrationListRow | undefined }> {
  let loaded = await load();
  if (!loaded.ok) return { ok: false };
  let row = findIntegrationRow(loaded.rows, platform);
  if (row?.connected) return { ok: true, row };
  for (const ms of delays) {
    await sleepMs(ms);
    loaded = await load();
    if (!loaded.ok) return { ok: false };
    row = findIntegrationRow(loaded.rows, platform);
    if (row?.connected) return { ok: true, row };
  }
  return { ok: true, row };
}
