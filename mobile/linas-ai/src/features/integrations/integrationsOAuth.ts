import { Linking } from 'react-native';
import { z } from 'zod';

import { apiFetch } from '../../api/client';

export const StartSchema = z.object({
  success: z.literal(true),
  authorization_url: z.string().url(),
});

export const DisconnectSchema = z.object({
  success: z.literal(true),
  platform: z.string(),
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
  const started = await apiFetch(path, {
    method: 'POST',
    body,
    schema: StartSchema,
  });
  await Linking.openURL(started.authorization_url);
}

export async function disconnectMetaPlatform(platform: 'instagram' | 'facebook'): Promise<void> {
  await apiFetch(`/api/mobile/integrations/${encodeURIComponent(platform)}/disconnect`, {
    method: 'POST',
    schema: DisconnectSchema,
  });
}
