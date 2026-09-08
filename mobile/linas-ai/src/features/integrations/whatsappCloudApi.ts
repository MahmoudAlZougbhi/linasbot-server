import { z } from 'zod';

import { apiFetch } from '../../api/client';

export { startWhatsAppCloudConnect, WhatsAppConnectError } from './whatsappCloudConnect';
export type { WhatsAppConnectErrorCode } from './whatsappCloudConnect';

export const WhatsAppStatusSchema = z.object({
  success: z.literal(true),
  platform: z.literal('whatsapp').optional(),
  lifecycle_status: z.string(),
  connectable: z.boolean(),
  coming_soon: z.boolean().optional(),
  awaiting_meta_approval: z.boolean().optional(),
  public_availability: z.boolean().optional(),
  pilot_entitled: z.boolean().optional(),
  blocker_code: z.string().nullable().optional(),
  blocker_message: z.string().nullable().optional(),
  connection: z
    .object({
      connection_id: z.string(),
      lifecycle_status: z.string(),
      connection_source: z.enum(['embedded_signup', 'meta_app_review_test']).optional(),
      display_phone_number: z.string().optional(),
      display_phone_last4: z.string().optional(),
      verified_name: z.string().optional(),
      ai_eligible: z.boolean().optional(),
      ai_default_enabled: z.boolean().optional(),
      calls_enabled: z.boolean().optional(),
      health_status: z.string().optional(),
      coexistence_mode: z.string().optional(),
      rollout_blocked_reason: z.string().nullable().optional(),
    })
    .nullable()
    .optional(),
  flags: z
    .object({
      connection_ui_enabled: z.boolean(),
      ai_replies_enabled: z.boolean().optional(),
      outbound_sends_enabled: z.boolean().optional(),
      public_availability: z.boolean().optional(),
      require_pilot_entitlement: z.boolean().optional(),
      embedded_signup_config_configured: z.boolean().optional(),
    })
    .optional(),
});

export type WhatsAppCloudStatus = z.infer<typeof WhatsAppStatusSchema>;

const OkSchema = z.object({ success: z.literal(true) }).passthrough();

export async function fetchWhatsAppCloudStatus(): Promise<WhatsAppCloudStatus> {
  return apiFetch('/api/whatsapp/cloud/status', { schema: WhatsAppStatusSchema });
}

export async function disconnectWhatsAppCloud(connectionId: string): Promise<void> {
  await apiFetch(`/api/whatsapp/cloud/connections/${encodeURIComponent(connectionId)}/disconnect`, {
    method: 'POST',
    body: JSON.stringify({ confirm: 'DISCONNECT' }),
    schema: OkSchema,
  });
}

export async function setWhatsAppAiEnabled(connectionId: string, enabled: boolean): Promise<void> {
  const path = enabled
    ? `/api/whatsapp/cloud/connections/${encodeURIComponent(connectionId)}/ai/enable`
    : `/api/whatsapp/cloud/connections/${encodeURIComponent(connectionId)}/ai/disable`;
  await apiFetch(path, { method: 'POST', schema: OkSchema });
}

export async function setWhatsAppCallsEnabled(connectionId: string, enabled: boolean): Promise<void> {
  const path = enabled
    ? `/api/whatsapp/cloud/connections/${encodeURIComponent(connectionId)}/calls/enable`
    : `/api/whatsapp/cloud/connections/${encodeURIComponent(connectionId)}/calls/disable`;
  await apiFetch(path, { method: 'POST', schema: OkSchema });
}
