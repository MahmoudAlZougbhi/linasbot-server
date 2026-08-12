import * as Google from 'expo-auth-session/providers/google';
import * as WebBrowser from 'expo-web-browser';
import { z } from 'zod';

import { apiFetch, ApiError } from '../../api/client';
import { MobileLoginResponseSchema } from '../../api/types';
import { tokenStore } from '../../auth/tokenStore';

WebBrowser.maybeCompleteAuthSession();

export type GoogleSignInResult =
  | { ok: true }
  | { ok: false; code: 'cancel' | 'unavailable' | 'link_required' | 'error'; message?: string; emailHint?: string };

const LinkRequiredSchema = z
  .object({
    code: z.literal('link_required'),
    email_hint: z.string().optional(),
  })
  .passthrough();

function clientIds() {
  const web = (process.env.EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID || '').trim();
  const ios = (process.env.EXPO_PUBLIC_GOOGLE_IOS_CLIENT_ID || '').trim();
  const android = (process.env.EXPO_PUBLIC_GOOGLE_ANDROID_CLIENT_ID || '').trim();
  return { web, ios, android };
}

/** True when a web client id is configured (required for ID-token Google Sign-In). */
export function isGoogleSignInConfigured(): boolean {
  return Boolean(clientIds().web);
}

/** Call from a React component — returns AuthSession Google ID-token request triple. */
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
