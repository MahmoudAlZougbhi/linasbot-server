import * as WebBrowser from 'expo-web-browser';
import { z } from 'zod';

import { ApiError, apiFetch } from '../../api/client';

WebBrowser.maybeCompleteAuthSession();

const ConnectStartSchema = z.object({
  success: z.literal(true),
  authorization_url: z.string().url(),
  correlation_id: z.string().optional(),
});

export type WhatsAppConnectErrorCode =
  | 'connect_in_progress'
  | 'invalid_authorization_url'
  | 'browser_unavailable'
  | 'cancelled'
  | 'failed';

export class WhatsAppConnectError extends Error {
  readonly code: WhatsAppConnectErrorCode;

  constructor(code: WhatsAppConnectErrorCode, message: string) {
    super(message);
    this.name = 'WhatsAppConnectError';
    this.code = code;
  }
}

const MOBILE_RETURN_URL = 'linasai://integrations';

let connectInFlight = false;

/** Test seam — reset in-flight lock between unit checks. */
export function resetWhatsAppConnectLockForTests(): void {
  connectInFlight = false;
}

export function isWhatsAppConnectInFlight(): boolean {
  return connectInFlight;
}

function assertHttpsAuthorizationUrl(url: string): void {
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    throw new WhatsAppConnectError(
      'invalid_authorization_url',
      'Server returned an invalid WhatsApp authorization URL',
    );
  }
  if (parsed.protocol !== 'https:') {
    throw new WhatsAppConnectError(
      'invalid_authorization_url',
      'WhatsApp authorization URL must be HTTPS',
    );
  }
  if (!parsed.pathname.includes('/integrations/whatsapp/')) {
    throw new WhatsAppConnectError(
      'invalid_authorization_url',
      'WhatsApp authorization URL is not the Embedded Signup bridge',
    );
  }
}

/**
 * Starts WhatsApp Cloud Embedded Signup via in-app auth session.
 * Avoids the Build 40 crash path (dynamic react-native import + system browser handoff).
 */
export async function startWhatsAppCloudConnect(): Promise<void> {
  if (connectInFlight) {
    throw new WhatsAppConnectError(
      'connect_in_progress',
      'WhatsApp connect is already in progress',
    );
  }
  connectInFlight = true;
  try {
    const started = await apiFetch('/api/whatsapp/cloud/connect/start', {
      method: 'POST',
      body: JSON.stringify({ return_surface: 'mobile' }),
      schema: ConnectStartSchema,
    });
    assertHttpsAuthorizationUrl(started.authorization_url);

    let result: WebBrowser.WebBrowserAuthSessionResult;
    try {
      result = await WebBrowser.openAuthSessionAsync(
        started.authorization_url,
        MOBILE_RETURN_URL,
      );
    } catch {
      throw new WhatsAppConnectError(
        'browser_unavailable',
        'Could not open Meta WhatsApp Embedded Signup',
      );
    }

    if (result.type === 'cancel' || result.type === 'dismiss') {
      throw new WhatsAppConnectError('cancelled', 'WhatsApp authorization was cancelled');
    }
    if (result.type === 'success') {
      const returned = result.url || '';
      if (/wa_connection=(failed|cancelled|canceled)/i.test(returned)) {
        throw new WhatsAppConnectError(
          /cancelled|canceled/i.test(returned) ? 'cancelled' : 'failed',
          'WhatsApp authorization did not complete',
        );
      }
      return;
    }
    throw new WhatsAppConnectError(
      'browser_unavailable',
      'Meta WhatsApp Embedded Signup did not complete',
    );
  } catch (err) {
    if (err instanceof WhatsAppConnectError || err instanceof ApiError) {
      throw err;
    }
    throw new WhatsAppConnectError(
      'browser_unavailable',
      'Could not start WhatsApp Embedded Signup',
    );
  } finally {
    connectInFlight = false;
  }
}
