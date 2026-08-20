import * as WebBrowser from 'expo-web-browser';
import { Linking } from 'react-native';
import { z } from 'zod';

import { ApiError, apiFetch } from '../../api/client';

WebBrowser.maybeCompleteAuthSession();

export const StartSchema = z.object({
  success: z.literal(true),
  authorization_url: z.string().url(),
});

export const DisconnectSchema = z.object({
  success: z.literal(true),
  platform: z.string(),
});

const MOBILE_RETURN_SURFACE = 'mobile' as const;
const MOBILE_RETURN_URL = 'linasai://integrations';

export type MetaOAuthConnectErrorCode =
  | 'invalid_authorization_url'
  | 'browser_unavailable'
  | 'cancelled'
  | 'failed';

export class MetaOAuthConnectError extends Error {
  readonly code: MetaOAuthConnectErrorCode;

  constructor(code: MetaOAuthConnectErrorCode, message: string) {
    super(message);
    this.name = 'MetaOAuthConnectError';
    this.code = code;
  }
}

function assertHttpsAuthorizationUrl(url: string): void {
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    throw new MetaOAuthConnectError(
      'invalid_authorization_url',
      'Server returned an invalid authorization URL',
    );
  }
  if (parsed.protocol !== 'https:') {
    throw new MetaOAuthConnectError(
      'invalid_authorization_url',
      'Authorization URL must be HTTPS',
    );
  }
}

/** Meta's mobile Instagram Login fix; no-op for Facebook authorize URLs. */
export function withInstagramMobileReauth(url: string): string {
  const parsed = new URL(url);
  if (parsed.hostname !== 'www.instagram.com') return url;
  if (!parsed.searchParams.has('force_reauth')) {
    parsed.searchParams.set('force_reauth', 'true');
  }
  return parsed.toString();
}

export function apiErrorDetail(err: ApiError): string | null {
  const body = err.body;
  if (!body || typeof body !== 'object') return null;
  const rec = body as Record<string, unknown>;
  for (const key of ['detail', 'message', 'error'] as const) {
    const value = rec[key];
    if (typeof value === 'string' && value.trim()) return value.trim();
  }
  return null;
}

export async function startMetaOAuth(platform: 'instagram' | 'facebook'): Promise<void> {
  const path =
    platform === 'instagram'
      ? '/api/meta/connections/instagram-login/start'
      : '/api/meta/connections/start';
  const body =
    platform === 'facebook'
      ? JSON.stringify({ channel: 'facebook', return_surface: MOBILE_RETURN_SURFACE })
      : JSON.stringify({ return_surface: MOBILE_RETURN_SURFACE });
  const started = await apiFetch(path, {
    method: 'POST',
    body,
    schema: StartSchema,
  });
  const authorizationUrl =
    platform === 'instagram'
      ? withInstagramMobileReauth(started.authorization_url)
      : started.authorization_url;
  assertHttpsAuthorizationUrl(authorizationUrl);

  let result: WebBrowser.WebBrowserAuthSessionResult;
  try {
    result = await WebBrowser.openAuthSessionAsync(authorizationUrl, MOBILE_RETURN_URL);
  } catch {
    throw new MetaOAuthConnectError(
      'browser_unavailable',
      'Could not open Meta authorization',
    );
  }

  if (result.type === 'cancel' || result.type === 'dismiss') {
    throw new MetaOAuthConnectError('cancelled', 'Meta authorization was cancelled');
  }
  if (result.type === 'success') {
    const returned = result.url || '';
    if (/meta_connection=(cancelled|canceled)/i.test(returned)) {
      throw new MetaOAuthConnectError('cancelled', 'Meta authorization was cancelled');
    }
    if (/meta_connection=failed/i.test(returned)) {
      throw new MetaOAuthConnectError('failed', 'Meta authorization did not complete');
    }
    return;
  }
  throw new MetaOAuthConnectError(
    'browser_unavailable',
    'Meta authorization did not complete',
  );
}

export async function disconnectMetaPlatform(platform: 'instagram' | 'facebook'): Promise<void> {
  await apiFetch(`/api/mobile/integrations/${encodeURIComponent(platform)}/disconnect`, {
    method: 'POST',
    schema: DisconnectSchema,
  });
}

export async function startTikTokOAuth(): Promise<void> {
  const started = await apiFetch('/api/tiktok/connect/start', {
    method: 'POST',
    body: JSON.stringify({ return_surface: MOBILE_RETURN_SURFACE }),
    schema: StartSchema,
  });
  await Linking.openURL(started.authorization_url);
}

export async function disconnectTikTok(): Promise<void> {
  await apiFetch('/api/tiktok/disconnect', {
    method: 'POST',
    schema: DisconnectSchema,
  });
}
