import { z } from 'zod';

export const TogglesSchema = z.object({
  dm: z.boolean(),
  comments: z.boolean(),
});

export const CapabilityStateSchema = z
  .object({
    requested_enabled: z.boolean(),
    permission_present: z.boolean(),
    webhook_subscribed: z.boolean(),
    tenant_action_enabled: z.boolean().optional(),
    connection_healthy: z.boolean().optional(),
    live_verified: z.boolean(),
    effective_enabled: z.boolean(),
    missing_scopes: z.array(z.string()).optional(),
    blocker: z.string().nullable().optional(),
    blocker_code: z.string().nullable().optional(),
    blocker_message: z.string().nullable().optional(),
    status: z.string().optional(),
    last_checked_at: z.number().optional(),
  })
  .optional();

export const RowSchema = z.object({
  platform: z.string(),
  label: z.string(),
  connected: z.boolean(),
  coming_soon: z.boolean().optional(),
  connectable: z.boolean().optional(),
  binding_ids: z.array(z.string()).optional(),
  toggles: TogglesSchema.optional(),
  comments_blocker: z.string().optional(),
  comments_state: CapabilityStateSchema,
  dm_state: CapabilityStateSchema,
  capabilities: z.record(z.string(), z.unknown()).optional(),
});

export const ListSchema = z.object({
  success: z.literal(true),
  integrations: z.array(RowSchema),
});

export const ToggleResponseSchema = z.object({
  success: z.literal(true),
  platform: z.string(),
  toggles: TogglesSchema,
  comments_state: CapabilityStateSchema,
  dm_state: CapabilityStateSchema,
});

export type IntegrationListRow = z.infer<typeof RowSchema>;
