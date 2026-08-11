import { z } from 'zod';

import { apiFetch } from '../../api/client';

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
      display_phone_last4: z.string().optional(),
      verified_name: z.string().optional(),
      ai_eligible: z.boolean().optional(),
      ai_default_enabled: z.boolean().optional(),
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

const StartSchema = z.object({
  success: z.literal(true),
  authorization_url: z.string().url(),
  correlation_id: z.string().optional(),
});

const OkSchema = z.object({ success: z.literal(true) }).passthrough();

const ConversationSchema = z.object({
  conversation_id: z.string(),
  connection_id: z.string(),
  control_state: z.string(),
  control_epoch: z.number().optional(),
  pause_reason: z.string().nullable().optional(),
  customer_wa_id_masked: z.string().optional(),
  customer_profile_name: z.string().optional(),
});

export type WhatsAppConversationRow = z.infer<typeof ConversationSchema>;

export async function fetchWhatsAppCloudStatus(): Promise<WhatsAppCloudStatus> {
  return apiFetch('/api/whatsapp/cloud/status', { schema: WhatsAppStatusSchema });
}

export async function startWhatsAppCloudConnect(): Promise<void> {
  const { Linking } = await import('react-native');
  const started = await apiFetch('/api/whatsapp/cloud/connect/start', {
    method: 'POST',
    body: JSON.stringify({ return_surface: 'mobile' }),
    schema: StartSchema,
  });
  await Linking.openURL(started.authorization_url);
}

export async function setWhatsAppAiEnabled(connectionId: string, enabled: boolean): Promise<void> {
  const path = enabled
    ? `/api/whatsapp/cloud/connections/${encodeURIComponent(connectionId)}/ai/enable`
    : `/api/whatsapp/cloud/connections/${encodeURIComponent(connectionId)}/ai/disable`;
  await apiFetch(path, { method: 'POST', schema: OkSchema });
}

export async function sendWhatsAppTestMessage(
  connectionId: string,
  toWaId: string,
  text: string,
): Promise<{ provider_wamid?: string | null }> {
  return apiFetch(`/api/whatsapp/cloud/connections/${encodeURIComponent(connectionId)}/test-message`, {
    method: 'POST',
    body: JSON.stringify({ to_wa_id: toWaId, text }),
    schema: OkSchema.extend({
      provider_wamid: z.string().nullable().optional(),
      to_wa_id_masked: z.string().optional(),
    }),
  });
}

export async function createWhatsAppTemplate(
  connectionId: string,
  input: { name: string; body_text: string; language?: string; category?: string },
): Promise<{ template?: { id?: string; status?: string; name?: string } }> {
  return apiFetch(`/api/whatsapp/cloud/connections/${encodeURIComponent(connectionId)}/templates`, {
    method: 'POST',
    body: JSON.stringify(input),
    schema: OkSchema.extend({
      template: z
        .object({
          id: z.string().optional(),
          status: z.string().optional(),
          name: z.string().optional(),
          language: z.string().optional(),
          category: z.string().optional(),
        })
        .optional(),
    }),
  });
}

export async function listWhatsAppConversations(connectionId: string): Promise<WhatsAppConversationRow[]> {
  const res = await apiFetch(
    `/api/whatsapp/cloud/connections/${encodeURIComponent(connectionId)}/conversations`,
    {
      schema: z.object({
        success: z.literal(true),
        conversations: z.array(ConversationSchema),
      }),
    },
  );
  return res.conversations;
}

export async function pauseWhatsAppConversation(conversationId: string): Promise<void> {
  await apiFetch(`/api/whatsapp/cloud/conversations/${encodeURIComponent(conversationId)}/pause`, {
    method: 'POST',
    schema: OkSchema,
  });
}

export async function resumeWhatsAppConversation(conversationId: string): Promise<void> {
  await apiFetch(`/api/whatsapp/cloud/conversations/${encodeURIComponent(conversationId)}/resume`, {
    method: 'POST',
    schema: OkSchema,
  });
}
