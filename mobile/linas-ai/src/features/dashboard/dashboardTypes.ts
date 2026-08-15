import { z } from 'zod';

const ActionSchema = z
  .object({
    code: z.string(),
    label: z.string(),
  })
  .nullable()
  .optional();

const AvailabilitySchema = z.enum(['ok', 'empty', 'error', 'unavailable']);

export const DashboardPeriodIdSchema = z.enum(['billing', '7d', '30d', 'custom', 'today']);
export type DashboardPeriodId = z.infer<typeof DashboardPeriodIdSchema>;

const ChannelCardSchema = z.object({
  platform: z.string(),
  capability: z.string(),
  connected: z.boolean(),
  enabled: z.boolean(),
  membership_allows: z.boolean(),
  permission_present: z.boolean(),
  webhook_subscribed: z.boolean().optional(),
  connection_healthy: z.boolean(),
  operational: z.boolean(),
  live_verified: z.boolean().optional(),
  status: z.string().nullable().optional(),
  blocker_code: z.string().nullable().optional(),
  blocker_message: z.string().nullable().optional(),
  interactions: z.number().nullable().optional(),
  credits_used: z.number().nullable().optional(),
  credits_used_available: z.boolean().optional(),
  action: ActionSchema,
});

export const TenantDashboardSchema = z.object({
  success: z.literal(true),
  generated_at: z.string(),
  period: z.object({
    id: DashboardPeriodIdSchema,
    label: z.string(),
    timezone: z.string(),
    start: z.string(),
    end: z.string(),
    custom_start: z.string().nullable().optional(),
    custom_end: z.string().nullable().optional(),
  }),
  workspace: z.object({
    tenant_id: z.string(),
    workspace_name: z.string(),
    workspace_name_source: z.string().optional(),
  }),
  workspace_status: z.object({
    state: z.string(),
    reason_code: z.string(),
    title: z.string(),
    explanation: z.string(),
    primary_action: ActionSchema,
  }),
  plan_and_credits: z
    .object({
      availability: AvailabilitySchema,
      error_code: z.string().optional(),
      message: z.string().optional(),
      plan_id: z.string().nullable().optional(),
      plan_name: z.string().nullable().optional(),
      subscription_status: z.string().nullable().optional(),
      subscription_exempt: z.boolean().optional(),
      current_period_end: z.string().nullable().optional(),
      included_credits: z.number().optional(),
      purchased_or_promotional_credits: z.number().optional(),
      reserved_credits: z.number().optional(),
      available_credits: z.number().optional(),
      total_available_credits: z.number().optional(),
      credits_consumed_period_estimate: z.number().optional(),
      credits_limit: z.number().optional(),
      usage_progress_ratio: z.number().nullable().optional(),
      credit_source_note: z.string().optional(),
      has_subscription: z.boolean().optional(),
      faq_used_entries: z.number().nullable().optional(),
      faq_max_entries: z.number().nullable().optional(),
      faq_quota_display: z.string().nullable().optional(),
      actions: z
        .object({
          manage_subscription: z.boolean().optional(),
          upgrade_plan: z.boolean().optional(),
          buy_credits: z.boolean().optional(),
        })
        .optional(),
    })
    .passthrough(),
  usage_summary: z
    .object({
      availability: AvailabilitySchema,
      error_code: z.string().optional(),
      message: z.string().optional(),
      total_interactions: z.number().optional(),
      successful_interactions: z.number().optional(),
      failed_interactions: z.number().optional(),
      success_rate: z.number().nullable().optional(),
      instagram_dms: z.number().nullable().optional(),
      facebook_dms: z.number().nullable().optional(),
      instagram_comments: z.number().nullable().optional(),
      facebook_comments: z.number().nullable().optional(),
      owner_copilot: z.number().nullable().optional(),
      content_management_ai: z.number().nullable().optional(),
      time_series: z
        .array(z.object({ date: z.string(), interactions: z.number() }))
        .optional(),
      credits_by_bucket_available: z.boolean().optional(),
      credits_by_bucket_note: z.string().optional(),
    })
    .passthrough(),
  usage_distribution: z
    .object({
      availability: AvailabilitySchema.optional(),
      mode_default: z.string().optional(),
      modes_supported: z.array(z.string()).optional(),
      credits_mode_available: z.boolean().optional(),
      credits_mode_note: z.string().nullable().optional(),
      items: z
        .array(
          z.object({
            bucket: z.string(),
            interactions: z.number(),
            failed: z.number().optional(),
            credits: z.number().nullable().optional(),
            credits_available: z.boolean().optional(),
          }),
        )
        .optional(),
      total_interactions: z.number().nullable().optional(),
      error_code: z.string().optional(),
      message: z.string().optional(),
    })
    .passthrough(),
  channels: z
    .object({
      availability: AvailabilitySchema,
      error_code: z.string().optional(),
      message: z.string().optional(),
      any_connected: z.boolean().optional(),
      membership_allows_comments: z.boolean().optional(),
      channels: z.array(ChannelCardSchema).optional(),
    })
    .passthrough(),
  content_readiness: z
    .object({
      availability: AvailabilitySchema,
      error_code: z.string().optional(),
      message: z.string().optional(),
      percent: z.number().optional(),
      sections_present: z.number().optional(),
      sections_total: z.number().optional(),
      published: z.boolean().optional(),
      draft_vs_published: z.string().optional(),
      last_published_at: z.string().nullable().optional(),
      missing_sections: z.array(z.string()).optional(),
      weak_sections: z.array(z.string()).optional(),
      off_days_status: z.string().optional(),
      faq_used: z.number().nullable().optional(),
      faq_max: z.number().nullable().optional(),
      faq_quota_display: z.string().nullable().optional(),
    })
    .passthrough(),
  team_capacity: z
    .object({
      availability: AvailabilitySchema,
      error_code: z.string().optional(),
      message: z.string().optional(),
      owner: z
        .object({
          id: z.string().nullable().optional(),
          name: z.string().nullable().optional(),
          email: z.string().nullable().optional(),
        })
        .nullable()
        .optional(),
      active_additional_users: z.number().optional(),
      pending_invitations: z.number().optional(),
      pending_invitations_note: z.string().optional(),
      additional_seat_allowance: z.number().nullable().optional(),
      additional_seats_unlimited: z.boolean().optional(),
      remaining_seats: z.number().nullable().optional(),
    })
    .passthrough(),
  alerts: z.array(
    z.object({
      severity: z.string(),
      reason_code: z.string(),
      title: z.string(),
      explanation: z.string(),
      timestamp: z.string(),
      action: ActionSchema,
    }),
  ),
  activity_summary: z
    .object({
      availability: AvailabilitySchema,
      error_code: z.string().optional(),
      message: z.string().optional(),
      total_activity: z
        .object({
          messages_replied: z.number(),
          comments_replied: z.number(),
          smart_answers: z.number(),
          requests: z.number(),
        })
        .optional(),
      channels: z
        .array(
          z.object({
            platform: z.string(),
            connected: z.boolean(),
            operational: z.boolean(),
            coming_soon: z.boolean().optional(),
            messages: z.number(),
            comments: z.number(),
            smart: z.number(),
            requests: z.number(),
            credits: z.number(),
          }),
        )
        .optional(),
      owner_copilot: z
        .object({
          credits: z.number(),
          chats: z.number(),
          users: z.number(),
          by_user: z
            .array(
              z.object({
                user_id: z.string().nullable().optional(),
                name: z.string().nullable().optional(),
                chats: z.number(),
                credits: z.number(),
                unattributed: z.boolean().optional(),
              }),
            )
            .optional(),
          interactions: z.number().optional(),
          credits_source: z.string().optional(),
        })
        .optional(),
      requests_source: z.string().optional(),
      credits_by_channel_note: z.string().optional(),
    })
    .passthrough(),
  partial_failures: z.array(z.string()).optional(),
  privacy: z
    .object({
      excludes_openai_usd: z.boolean().optional(),
      excludes_global_owner_metrics: z.boolean().optional(),
      excludes_other_tenants: z.boolean().optional(),
      excludes_company_profit_fields: z.boolean().optional(),
    })
    .optional(),
});

export type TenantDashboard = z.infer<typeof TenantDashboardSchema>;
export type DashboardAction = { code: string; label: string };
export type DashboardNavigateTarget =
  | 'chat'
  | 'integrations'
  | 'cm'
  | 'faq'
  | 'users'
  | 'subscription'
  | 'buy_credits';
