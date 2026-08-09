import { z } from 'zod';

import { ApiError, apiFetch } from '../../api/client';

const OwnerNotificationSchema = z.object({
  id: z.string(),
  type: z.string(),
  title_en: z.string().optional().nullable(),
  title_ar: z.string().optional().nullable(),
  customer_name: z.string().optional().nullable(),
  user_id: z.string().optional().nullable(),
  conversation_id: z.string().optional().nullable(),
  channel: z.string().optional().nullable(),
  escalation_reason: z.string().optional().nullable(),
  last_message: z.string().optional().nullable(),
  trigger_source: z.string().optional().nullable(),
  created_at: z.number().optional().nullable(),
  read: z.boolean().optional().nullable(),
  deep_link: z
    .object({
      screen: z.string().optional().nullable(),
      user_id: z.string().optional().nullable(),
      conversation_id: z.string().optional().nullable(),
    })
    .optional()
    .nullable(),
});

const ListSchema = z.object({
  success: z.boolean(),
  notifications: z.array(OwnerNotificationSchema).optional(),
  unread_count: z.number().optional(),
  error: z.string().optional(),
});

const MutateSchema = z.object({
  success: z.boolean(),
  notification: OwnerNotificationSchema.optional(),
  marked: z.number().optional(),
  error: z.string().optional(),
});

const DeviceTokenSchema = z.object({
  success: z.boolean(),
  registered: z.boolean().optional(),
  push_delivery: z.string().optional(),
  error: z.string().optional(),
});

export type OwnerNotification = z.infer<typeof OwnerNotificationSchema>;

export type NotificationsErrorKind = 'auth' | 'forbidden' | 'other';

export function classifyNotificationsError(err: unknown): NotificationsErrorKind {
  if (err instanceof ApiError) {
    if (err.status === 401) return 'auth';
    if (err.status === 403) return 'forbidden';
  }
  return 'other';
}

export async function listOwnerNotifications(opts?: {
  limit?: number;
  unreadOnly?: boolean;
}): Promise<{ notifications: OwnerNotification[]; unreadCount: number }> {
  const params = new URLSearchParams();
  if (opts?.limit) params.set('limit', String(opts.limit));
  if (opts?.unreadOnly) params.set('unread_only', 'true');
  const q = params.toString();
  const body = await apiFetch(`/api/owner-notifications${q ? `?${q}` : ''}`, {
    method: 'GET',
    schema: ListSchema,
  });
  if (!body.success) {
    throw new ApiError(body.error || 'Failed to load notifications', 400, body);
  }
  return {
    notifications: body.notifications ?? [],
    unreadCount: body.unread_count ?? 0,
  };
}

export async function markNotificationRead(id: string): Promise<void> {
  const body = await apiFetch(`/api/owner-notifications/${encodeURIComponent(id)}/read`, {
    method: 'POST',
    schema: MutateSchema,
  });
  if (!body.success) {
    throw new ApiError(body.error || 'Failed to mark read', 400, body);
  }
}

export async function markAllNotificationsRead(): Promise<void> {
  const body = await apiFetch('/api/owner-notifications/read-all', {
    method: 'POST',
    schema: MutateSchema,
  });
  if (!body.success) {
    throw new ApiError(body.error || 'Failed to mark all read', 400, body);
  }
}

/** Scaffolding only — server stores token; push send needs infra approval. */
export async function registerPushDeviceToken(input: {
  token: string;
  platform?: string;
  expoProjectId?: string;
}): Promise<{ pushDelivery: string }> {
  const body = await apiFetch('/api/owner-notifications/device-token', {
    method: 'POST',
    schema: DeviceTokenSchema,
    body: JSON.stringify({
      token: input.token,
      platform: input.platform,
      expo_project_id: input.expoProjectId,
    }),
  });
  if (!body.success) {
    throw new ApiError(body.error || 'Failed to register device token', 400, body);
  }
  return { pushDelivery: body.push_delivery || 'disabled_pending_infra_approval' };
}
