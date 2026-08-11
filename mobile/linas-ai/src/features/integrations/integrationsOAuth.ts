import { Linking } from 'react-native';
import { z } from 'zod';

import { apiFetch } from '../../api/client';

export const StartSchema = z.object({
  success: z.literal(true),
  authorization_url: z.string().url(),
});

export const DisconnectSchema = z.object({
  success: z.literal(true),
});

const MOBILE_RETURN_SURFACE = 'mobile' as const;

export async function startMetaOAuth(platform: 'instagram' | 'facebook'): Promise<void> {
  const path =
    platform === 'instagram'
      ? '/api/meta/connections/instagram-login/start'
      : '/api/meta/connections/start';
  const body =
    platform === 'facebook'
      ? JSON.stringify({ channel: 'facebook', return_surface: MOBILE_RETURN_SURFACE })
      : JSON.stringify({ return_surface: MOBILE_RETURN_SURFACE });
  // Instagram Connect must use Instagram Login only — never Facebook Login for Business.
  const started = await apiFetch(path, {
    method: 'POST',
    body,
    schema: StartSchema,
  });
  await Linking.openURL(started.authorization_url);
}

export async function disconnectMetaBindings(bindingIds: string[]): Promise<void> {
  for (const bindingId of bindingIds) {
    await apiFetch(`/api/meta/connections/${encodeURIComponent(bindingId)}/disconnect`, {
      method: 'POST',
      schema: DisconnectSchema,
    });
  }
}
