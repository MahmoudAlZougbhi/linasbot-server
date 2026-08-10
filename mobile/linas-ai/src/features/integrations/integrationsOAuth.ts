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

export async function startMetaOAuth(platform: 'instagram' | 'facebook'): Promise<void> {
  const path =
    platform === 'instagram'
      ? '/api/meta/connections/instagram-login/start'
      : '/api/meta/connections/start';
  const body = platform === 'facebook' ? JSON.stringify({ channel: 'facebook' }) : undefined;
  try {
    const started = await apiFetch(path, {
      method: 'POST',
      body,
      schema: StartSchema,
    });
    await Linking.openURL(started.authorization_url);
    return;
  } catch (firstErr) {
    if (platform === 'instagram') {
      const started = await apiFetch('/api/meta/connections/start', {
        method: 'POST',
        body: JSON.stringify({ channel: 'instagram' }),
        schema: StartSchema,
      });
      await Linking.openURL(started.authorization_url);
      return;
    }
    throw firstErr;
  }
}

export async function disconnectMetaBindings(bindingIds: string[]): Promise<void> {
  for (const bindingId of bindingIds) {
    await apiFetch(`/api/meta/connections/${encodeURIComponent(bindingId)}/disconnect`, {
      method: 'POST',
      schema: DisconnectSchema,
    });
  }
}
