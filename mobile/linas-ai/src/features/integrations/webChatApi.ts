import { z } from 'zod';

import { apiFetch } from '../../api/client';
import { WebChatAppearanceSchema } from './webChatTypes';

export const WebChatSettingsSchema = z.object({
  widget_key: z.string(),
  integration_public_id: z.string(),
  site_url: z.string(),
  enabled: z.boolean(),
  connected: z.boolean(),
  operational: z.boolean(),
  installation_status: z.enum(['connected', 'waiting', 'disabled', 'domain_mismatch']),
  blocker_code: z.string().nullable().optional(),
  integration_mode: z.enum(['linas_widget', 'custom_chat']),
  appearance: WebChatAppearanceSchema,
  contrast_warnings: z.array(z.string()).optional(),
  installation: z.object({
    last_seen_at: z.number().nullable().optional(),
    last_origin: z.string(),
    installed: z.boolean(),
  }),
  embed_snippet: z.string(),
  widget_script_url: z.string(),
  sdk_docs_url: z.string().optional(),
  membership_allows: z.boolean().optional(),
  membership_message: z.string().nullable().optional(),
});

export type WebChatSettings = z.infer<typeof WebChatSettingsSchema>;

const WebChatEnvelopeSchema = z.object({
  success: z.literal(true),
  web_chat: WebChatSettingsSchema,
});

const CheckInstallSchema = z.object({
  success: z.literal(true),
  installation_status: WebChatSettingsSchema.shape.installation_status,
  installation: WebChatSettingsSchema.shape.installation,
});

export async function fetchWebChatSettings(): Promise<WebChatSettings> {
  const res = await apiFetch('/api/mobile/web-chat', {
    method: 'GET',
    schema: WebChatEnvelopeSchema,
  });
  return res.web_chat;
}

export async function saveWebChatSettings(body: {
  site_url?: string;
  enabled?: boolean;
  integration_mode?: 'linas_widget' | 'custom_chat';
  appearance?: WebChatSettings['appearance'];
}): Promise<WebChatSettings> {
  const res = await apiFetch('/api/mobile/web-chat', {
    method: 'PUT',
    body: JSON.stringify(body),
    schema: WebChatEnvelopeSchema,
  });
  return res.web_chat;
}

export async function rotateWebChatKey(): Promise<WebChatSettings> {
  const res = await apiFetch('/api/mobile/web-chat/rotate-key', {
    method: 'POST',
    body: '{}',
    schema: WebChatEnvelopeSchema,
  });
  return res.web_chat;
}

export async function checkWebChatInstallation(): Promise<{
  installation_status: WebChatSettings['installation_status'];
  installation: WebChatSettings['installation'];
}> {
  return apiFetch('/api/mobile/web-chat/check-installation', {
    method: 'POST',
    body: '{}',
    schema: CheckInstallSchema,
  });
}
