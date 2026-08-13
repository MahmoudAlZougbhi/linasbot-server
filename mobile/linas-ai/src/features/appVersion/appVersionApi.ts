import { z } from 'zod';

import { apiFetch } from '../../api/client';
import { APP_VERSION } from '../../config';

export const AppVersionStateSchema = z.enum(['up_to_date', 'update_available', 'force_update']);

export const AppVersionCheckSchema = z.object({
  success: z.literal(true),
  state: AppVersionStateSchema,
  installed_version: z.string(),
  latest_version: z.string(),
  min_supported_version: z.string(),
  ios_store_url: z.string().url().nullable().optional(),
  android_store_url: z.string().url().nullable().optional(),
});

export type AppVersionCheck = z.infer<typeof AppVersionCheckSchema>;

export async function checkAppVersion(): Promise<AppVersionCheck> {
  return apiFetch('/api/public/app-version/check', {
    method: 'POST',
    auth: false,
    body: JSON.stringify({
      installed_version: APP_VERSION,
    }),
    schema: AppVersionCheckSchema,
  });
}
