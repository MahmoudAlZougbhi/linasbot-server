import { z } from 'zod';

import { apiFetch } from '../../api/client';

export const FOLLOW_UP_GOALS = [
  'gentle_check_in',
  'offer_more_help',
  'politely_close',
] as const;

export type FollowUpGoal = (typeof FOLLOW_UP_GOALS)[number];

export const DEFAULT_STEP_DELAYS = [30, 360, 1200] as const;

const ChannelsEnabledSchema = z.object({
  whatsapp_cloud: z.boolean(),
  instagram_dm: z.boolean(),
  facebook_messenger: z.boolean(),
});

export type FollowUpChannelsEnabled = z.infer<typeof ChannelsEnabledSchema>;

const GoalSchema = z.enum(FOLLOW_UP_GOALS);

const StepSchema = z.object({
  step_index: z.number().int().min(1).max(3),
  enabled: z.boolean(),
  delay_minutes: z.number().int().positive(),
  goal: GoalSchema,
});

const BlockersSchema = z
  .object({
    whatsapp_connected: z.boolean().optional(),
    lifecycle_status: z.string().optional(),
    ai_eligible: z.boolean().optional(),
    ai_blocker: z.string().nullable().optional(),
    pilot_entitled: z.boolean().optional(),
    route_integrations_when_disconnected: z.boolean().optional(),
  })
  .passthrough();

export const SmartFollowUpSettingsSchema = z
  .object({
    success: z.literal(true),
    feature: z.string().optional(),
    feature_ar: z.string().optional(),
    enabled: z.boolean(),
    business_hours_only: z.boolean(),
    billing_mode: z.string().optional(),
    billing_manage_in_meta: z.boolean().optional(),
    settings_version: z.number().int(),
    updated_at: z.string().nullable().optional(),
    channels_enabled: ChannelsEnabledSchema.optional(),
    channels_supported: z.array(z.string()).optional(),
    steps: z.array(StepSchema).min(1).max(3),
    stop_rules: z.array(z.string()).optional(),
    message_policy: z
      .object({
        writer: z.string().optional(),
        absolute_delays: z.boolean().optional(),
        templates_customer_facing: z.boolean().optional(),
        marketing_forbidden: z.boolean().optional(),
      })
      .passthrough()
      .optional(),
    blockers: BlockersSchema.optional(),
  })
  .passthrough();

export type SmartFollowUpSettings = z.infer<typeof SmartFollowUpSettingsSchema>;
export type SmartFollowUpStep = z.infer<typeof StepSchema>;

const AnalyticsSchema = z
  .object({
    success: z.boolean().optional(),
    availability: z.string().optional(),
    metrics: z
      .object({
        sequences_started: z.number().optional(),
        followups_sent: z.number().optional(),
        cancelled: z.number().optional(),
        skipped: z.number().optional(),
        failed_or_reconciliation: z.number().optional(),
        customer_replies_after_followup: z.number().optional(),
        response_rate: z.number().optional(),
        ai_credits_consumed: z.number().optional(),
      })
      .passthrough()
      .optional(),
  })
  .passthrough();

export type SmartFollowUpAnalytics = z.infer<typeof AnalyticsSchema>;

const PreviewSchema = z
  .object({
    success: z.boolean(),
    preview_text: z.string().optional(),
    sends_whatsapp: z.boolean().optional(),
    uses_credits: z.boolean().optional(),
    disclosure: z.string().optional(),
    live_customer_result: z.boolean().optional(),
    error: z.string().optional(),
    message: z.string().optional(),
  })
  .passthrough();

export type SmartFollowUpPreview = z.infer<typeof PreviewSchema>;

export type SettingsUpdatePayload = {
  enabled: boolean;
  business_hours_only: boolean;
  settings_version: number;
  channels_enabled: FollowUpChannelsEnabled;
  steps: SmartFollowUpStep[];
};

export async function fetchSmartFollowUpSettings(): Promise<SmartFollowUpSettings> {
  return apiFetch('/api/whatsapp/smart-followup/settings', {
    schema: SmartFollowUpSettingsSchema,
  });
}

export async function saveSmartFollowUpSettings(
  payload: SettingsUpdatePayload,
): Promise<SmartFollowUpSettings> {
  return apiFetch('/api/whatsapp/smart-followup/settings', {
    method: 'PUT',
    body: JSON.stringify(payload),
    schema: SmartFollowUpSettingsSchema,
  });
}

export async function fetchSmartFollowUpAnalytics(
  period = '7d',
): Promise<SmartFollowUpAnalytics> {
  return apiFetch(`/api/whatsapp/smart-followup/analytics?period=${encodeURIComponent(period)}`, {
    schema: AnalyticsSchema,
  });
}

export async function previewSmartFollowUp(goal: FollowUpGoal): Promise<SmartFollowUpPreview> {
  return apiFetch('/api/whatsapp/smart-followup/preview', {
    method: 'POST',
    body: JSON.stringify({ goal }),
    schema: PreviewSchema,
  });
}

export function formatDelayLabel(minutes: number): string {
  if (minutes < 60) return `${minutes}m`;
  const hours = minutes / 60;
  if (Number.isInteger(hours)) return `${hours}h`;
  return `${Math.round(hours * 10) / 10}h`;
}

export function isMetaSetupBlocker(aiBlocker: string | null | undefined): boolean {
  if (!aiBlocker) return false;
  return (
    aiBlocker === 'scopes_missing' ||
    aiBlocker === 'pilot_required' ||
    aiBlocker === 'webhook_unhealthy' ||
    aiBlocker === 'health_unhealthy' ||
    aiBlocker === 'history_sync_in_progress'
  );
}

export function isAiDisabledBlocker(aiBlocker: string | null | undefined): boolean {
  if (!aiBlocker) return false;
  return aiBlocker === 'ai_default_off' || aiBlocker === 'ai_replies_flag_off';
}
