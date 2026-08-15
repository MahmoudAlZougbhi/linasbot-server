import { z } from 'zod';

import { apiFetch } from '../../api/client';

export const WebChatSettingsSchema = z.object({
  widget_key: z.string(),
  site_url: z.string(),
  enabled: z.boolean(),
  connected: z.boolean(),
  operational: z.boolean(),
  blocker_code: z.string().nullable().optional(),
  embed_snippet: z.string(),
  widget_script_url: z.string(),
  membership_allows: z.boolean().optional(),
  membership_message: z.string().nullable().optional(),
});

export type WebChatSettings = z.infer<typeof WebChatSettingsSchema>;

const WebChatEnvelopeSchema = z.object({
  success: z.literal(true),
  web_chat: WebChatSettingsSchema,
});

export async function fetchWebChatSettings(): Promise<WebChatSettings> {
  const res = await apiFetch('/api/mobile/web-chat', { method: 'GET' }, WebChatEnvelopeSchema);
  return res.web_chat;
}

export async function saveWebChatSettings(body: {
  site_url?: string;
  enabled?: boolean;
}): Promise<WebChatSettings> {
  const res = await apiFetch(
    '/api/mobile/web-chat',
    { method: 'PUT', body: JSON.stringify(body) },
    WebChatEnvelopeSchema,
  );
  return res.web_chat;
}

export async function rotateWebChatKey(): Promise<WebChatSettings> {
  const res = await apiFetch(
    '/api/mobile/web-chat/rotate-key',
    { method: 'POST', body: '{}' },
    WebChatEnvelopeSchema,
  );
  return res.web_chat;
}
