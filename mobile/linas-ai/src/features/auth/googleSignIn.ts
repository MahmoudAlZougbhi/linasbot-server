import * as Google from 'expo-auth-session/providers/google';
import * as WebBrowser from 'expo-web-browser';
import { Platform } from 'react-native';
import { z } from 'zod';

import { apiFetch, ApiError } from '../../api/client';
import { MobileLoginResponseSchema } from '../../api/types';
import { tokenStore } from '../../auth/tokenStore';
import {
  GOOGLE_ANDROID_CLIENT_ID,
  GOOGLE_IOS_CLIENT_ID,
  GOOGLE_WEB_CLIENT_ID,
} from '../../config';

WebBrowser.maybeCompleteAuthSession();

export type GoogleSignInResult =
  | { ok: true }
  | { ok: false; code: 'cancel' | 'unavailable' | 'link_required' | 'error'; message?: string; emailHint?: string };

export type GoogleClientIds = { web: string; ios: string; android: string };

const LinkRequiredSchema = z
  .object({
    code: z.literal('link_required'),
    email_hint: z.string().optional(),
  })
  .passthrough();

function clientIds(): GoogleClientIds {
  return {
    web: GOOGLE_WEB_CLIENT_ID,
    ios: GOOGLE_IOS_CLIENT_ID,
    android: GOOGLE_ANDROID_CLIENT_ID,
  };
}

/**
 * expo-auth-session throws if the platform client id is missing
 * (`iosClientId` on iOS, `androidClientId` on Android). Web still needs `clientId`.
 */
export function isGoogleAuthConfiguredForPlatform(
  ids: GoogleClientIds,
  platform: string,
): boolean {
  if (!ids.web) return false;
  if (platform === 'ios') return Boolean(ids.ios);
  if (platform === 'android') return Boolean(ids.android);
  return true;
}

/** True when Google Sign-In can run on this OS without throwing. */
export function isGoogleSignInConfigured(): boolean {
  return isGoogleAuthConfiguredForPlatform(clientIds(), Platform.OS);
}

/**
 * Call only from a component mounted when `isGoogleSignInConfigured()` is true.
 * expo-auth-session requires the platform client id and throws otherwise.
 */
export function useGoogleIdTokenAuthRequest() {
  const { web, ios, android } = clientIds();
  return Google.useIdTokenAuthRequest({
    clientId: web || undefined,
    iosClientId: ios || undefined,
    androidClientId: android || undefined,
    scopes: ['openid', 'profile', 'email'],
  });
}

export async function completeGoogleSignIn(params: {
  idToken: string;
  nonce?: string;
  fullName?: string;
  email?: string;
}): Promise<GoogleSignInResult> {
  if (!params.idToken) {
    return { ok: false, code: 'error', message: 'missing_identity_token' };
  }
  const body: Record<string, unknown> = {
    identity_token: params.idToken,
  };
  if (params.nonce) body.nonce = params.nonce;
  if (params.fullName) body.full_name = params.fullName;
  if (params.email) body.email = params.email;

  try {
    const result = await apiFetch('/api/auth/mobile/google', {
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
      message: err instanceof Error ? err.message : 'google_sign_in_network',
    };
  }
}
