import { Platform } from 'react-native';
import * as AppleAuthentication from 'expo-apple-authentication';
import { z } from 'zod';

import { apiFetch, ApiError } from '../../api/client';
import { tokenStore } from '../../auth/tokenStore';
import { randomAppleNonce, sha256HexNonce } from './appleNonce';

export type AppleAccountResult =
  | { ok: true }
  | { ok: false; code: 'cancel' | 'unavailable' | 'error'; message?: string };

const OkSchema = z.object({ success: z.boolean() }).passthrough();

async function ensureAppleAvailable(): Promise<AppleAccountResult | null> {
  if (Platform.OS !== 'ios') {
    return { ok: false, code: 'unavailable', message: 'apple_sign_in_ios_only' };
  }
  const available = await AppleAuthentication.isAvailableAsync();
  if (!available) {
    return { ok: false, code: 'unavailable', message: 'apple_sign_in_unavailable' };
  }
  return null;
}

/** Link Apple to the signed-in account → POST /api/auth/mobile/apple/link */
export async function linkApple(): Promise<AppleAccountResult> {
  const gate = await ensureAppleAvailable();
  if (gate) return gate;

  const rawNonce = randomAppleNonce();
  const hashedNonce = await sha256HexNonce(rawNonce);
  let credential: AppleAuthentication.AppleAuthenticationCredential;
  try {
    credential = await AppleAuthentication.signInAsync({
      requestedScopes: [
        AppleAuthentication.AppleAuthenticationScope.FULL_NAME,
        AppleAuthentication.AppleAuthenticationScope.EMAIL,
      ],
      nonce: hashedNonce,
    });
  } catch (err) {
    const code = (err as { code?: string })?.code;
    if (code === 'ERR_REQUEST_CANCELED' || code === 'ERR_CANCELED') {
      return { ok: false, code: 'cancel' };
    }
    return {
      ok: false,
      code: 'error',
      message: err instanceof Error ? err.message : 'apple_link_failed',
    };
  }

  if (!credential.identityToken) {
    return { ok: false, code: 'error', message: 'missing_identity_token' };
  }

  const body: Record<string, unknown> = {
    identity_token: credential.identityToken,
    nonce: rawNonce,
  };
  if (credential.authorizationCode) {
    body.authorization_code = credential.authorizationCode;
  }

  try {
    await apiFetch('/api/auth/mobile/apple/link', {
      method: 'POST',
      body: JSON.stringify(body),
      schema: OkSchema,
    });
    return { ok: true };
  } catch (err) {
    if (err instanceof ApiError) {
      return { ok: false, code: 'error', message: `http_${err.status}` };
    }
    return {
      ok: false,
      code: 'error',
      message: err instanceof Error ? err.message : 'apple_link_network',
    };
  }
}

/** Unlink Apple → POST /api/auth/mobile/apple/unlink */
export async function unlinkApple(): Promise<AppleAccountResult> {
  try {
    await apiFetch('/api/auth/mobile/apple/unlink', {
      method: 'POST',
      body: JSON.stringify({}),
      schema: OkSchema,
    });
    return { ok: true };
  } catch (err) {
    if (err instanceof ApiError) {
      return { ok: false, code: 'error', message: `http_${err.status}` };
    }
    return {
      ok: false,
      code: 'error',
      message: err instanceof Error ? err.message : 'apple_unlink_network',
    };
  }
}

/**
 * Delete account → POST /api/auth/mobile/account/delete
 * Optional authorizationCode improves Apple-side token revoke.
 * Clears tokenStore on success.
 */
export async function deleteAccount(opts?: {
  authorizationCode?: string | null;
}): Promise<AppleAccountResult> {
  const body: Record<string, unknown> = {};
  const code = (opts?.authorizationCode || '').trim();
  if (code) body.authorization_code = code;

  try {
    await apiFetch('/api/auth/mobile/account/delete', {
      method: 'POST',
      body: JSON.stringify(body),
      schema: OkSchema,
    });
    await tokenStore.clear();
    return { ok: true };
  } catch (err) {
    if (err instanceof ApiError) {
      return { ok: false, code: 'error', message: `http_${err.status}` };
    }
    return {
      ok: false,
      code: 'error',
      message: err instanceof Error ? err.message : 'apple_delete_network',
    };
  }
}
