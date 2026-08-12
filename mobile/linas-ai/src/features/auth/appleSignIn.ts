import { Platform } from 'react-native';
import * as AppleAuthentication from 'expo-apple-authentication';
import * as Crypto from 'expo-crypto';
import { z } from 'zod';

import { apiFetch, ApiError } from '../../api/client';
import { MobileLoginResponseSchema } from '../../api/types';
import { tokenStore } from '../../auth/tokenStore';

export type AppleSignInResult =
  | { ok: true }
  | { ok: false; code: 'cancel' | 'unavailable' | 'link_required' | 'error'; message?: string; emailHint?: string };

const LinkRequiredSchema = z
  .object({
    code: z.literal('link_required'),
    email_hint: z.string().optional(),
  })
  .passthrough();

function randomNonce(bytes = 32): string {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  let out = '';
  const arr = new Uint8Array(bytes);
  Crypto.getRandomValues(arr);
  for (let i = 0; i < arr.length; i++) {
    out += alphabet[arr[i]! % alphabet.length];
  }
  return out;
}

function fullNameFromCredential(
  name: AppleAuthentication.AppleAuthenticationFullName | null,
): string | undefined {
  if (!name) return undefined;
  const parts = [name.givenName, name.middleName, name.familyName]
    .map((p) => (typeof p === 'string' ? p.trim() : ''))
    .filter(Boolean);
  return parts.length ? parts.join(' ') : undefined;
}

/** Sign in with Apple → POST /api/auth/mobile/apple → store tokens. iOS only. */
export async function signInWithApple(): Promise<AppleSignInResult> {
  if (Platform.OS !== 'ios') {
    return { ok: false, code: 'unavailable', message: 'apple_sign_in_ios_only' };
  }

  const available = await AppleAuthentication.isAvailableAsync();
  if (!available) {
    return { ok: false, code: 'unavailable', message: 'apple_sign_in_unavailable' };
  }

  // Pass raw nonce; expo-apple-authentication SHA-256-hashes it before Apple.
  // Server compares claims.nonce to SHA-256(rawNonce).
  const rawNonce = randomNonce();

  let credential: AppleAuthentication.AppleAuthenticationCredential;
  try {
    credential = await AppleAuthentication.signInAsync({
      requestedScopes: [
        AppleAuthentication.AppleAuthenticationScope.FULL_NAME,
        AppleAuthentication.AppleAuthenticationScope.EMAIL,
      ],
      nonce: rawNonce,
    });
  } catch (err) {
    const code = (err as { code?: string })?.code;
    if (code === 'ERR_REQUEST_CANCELED' || code === 'ERR_CANCELED') {
      return { ok: false, code: 'cancel' };
    }
    return {
      ok: false,
      code: 'error',
      message: err instanceof Error ? err.message : 'apple_sign_in_failed',
    };
  }

  if (!credential.identityToken) {
    return { ok: false, code: 'error', message: 'missing_identity_token' };
  }

  const body: Record<string, unknown> = {
    identity_token: credential.identityToken,
    nonce: rawNonce,
  };
  const fullName = fullNameFromCredential(credential.fullName);
  if (fullName) body.full_name = fullName;
  if (credential.email) body.email = credential.email;
  if (credential.authorizationCode) {
    body.authorization_code = credential.authorizationCode;
  }

  try {
    const result = await apiFetch('/api/auth/mobile/apple', {
      method: 'POST',
      auth: false,
      body: JSON.stringify(body),
      schema: MobileLoginResponseSchema,
    });
    await tokenStore.setTokens(result.access_token, result.refresh_token);
    await tokenStore.setUser(result.user);
    return { ok: true };
  } catch (err) {
    if (err instanceof ApiError && err.status === 409) {
      const parsed = LinkRequiredSchema.safeParse(err.body);
      return {
        ok: false,
        code: 'link_required',
        emailHint: parsed.success ? parsed.data.email_hint : undefined,
        message: 'link_required',
      };
    }
    if (err instanceof ApiError) {
      return { ok: false, code: 'error', message: `http_${err.status}` };
    }
    return {
      ok: false,
      code: 'error',
      message: err instanceof Error ? err.message : 'apple_sign_in_network',
    };
  }
}
