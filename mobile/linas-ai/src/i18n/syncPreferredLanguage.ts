import { z } from 'zod';

import { apiFetch } from '../api/client';
import type { AppLanguage } from './index';

/** Best-effort: keep Owner Copilot preferred_language aligned with app UI locale. */
export async function syncPreferredLanguageToServer(lang: AppLanguage): Promise<void> {
  try {
    await apiFetch('/api/owner-ai/profile', {
      method: 'PATCH',
      body: JSON.stringify({ preferred_language: lang }),
      schema: z.object({ success: z.literal(true) }).passthrough(),
    });
  } catch {
    /* guest / offline / unauthenticated — local locale still applies via Accept-Language */
  }
}
