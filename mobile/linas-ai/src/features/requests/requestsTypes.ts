import { z } from 'zod';

import type { StringKey } from '../../i18n/locales/en';

export const REQUEST_TYPES = ['ORDER', 'APPOINTMENT', 'OTHER'] as const;
export type RequestType = (typeof REQUEST_TYPES)[number];

export const REQUEST_STATUSES = [
  'NEW',
  'IN_REVIEW',
  'WAITING_FOR_CUSTOMER',
  'CONFIRMED',
  'READY',
  'COMPLETED',
  'CANCELLED',
] as const;
export type RequestStatus = (typeof REQUEST_STATUSES)[number];

export const SOURCE_CHANNELS = [
  'instagram_dm',
  'facebook_messenger',
  'whatsapp_cloud',
  'comment_linked_dm',
] as const;

export const COUNTER_STATUSES = [
  'NEW',
  'IN_REVIEW',
  'WAITING_FOR_CUSTOMER',
  'CONFIRMED',
  'READY',
  'COMPLETED',
] as const;

export type TypeFilter = 'all' | RequestType;
export type DatePreset = 'all' | 'today' | 'last7' | 'last30';
export type AssigneeFilter = 'all' | 'me';

export const RequestCardSchema = z.object({
  request_id: z.string(),
  request_number: z.string(),
  request_type: z.string(),
  status: z.string(),
  source_channel: z.string().nullable().optional(),
  customer_display_name: z.string().nullable().optional(),
  platform_username: z.string().nullable().optional(),
  title: z.string().nullable().optional(),
  preferred_date: z.string().nullable().optional(),
  preferred_time: z.string().nullable().optional(),
  assigned_user_id: z.string().nullable().optional(),
  notification_status: z.string().nullable().optional(),
  created_at: z.string().nullable().optional(),
  row_version: z.number(),
});

export const RequestNoteSchema = z.object({
  id: z.string(),
  author_user_id: z.string().nullable().optional(),
  body: z.string(),
  created_at: z.string().nullable().optional(),
});

export const RequestEventSchema = z.object({
  id: z.string(),
  event_type: z.string(),
  actor_kind: z.string().nullable().optional(),
  actor_user_id: z.string().nullable().optional(),
  payload: z.record(z.string(), z.unknown()).nullable().optional(),
  created_at: z.string().nullable().optional(),
});

export const RequestDetailSchema = RequestCardSchema.extend({
  tenant_id: z.string().optional(),
  source_account_id: z.string().nullable().optional(),
  external_customer_id: z.string().nullable().optional(),
  customer_name: z.string().nullable().optional(),
  conversation_id: z.string().nullable().optional(),
  originating_message_id: z.string().nullable().optional(),
  originating_comment_id: z.string().nullable().optional(),
  collected_fields: z.unknown().optional(),
  requested_items: z.unknown().optional(),
  requested_branch: z.string().nullable().optional(),
  fulfillment_preference: z.string().nullable().optional(),
  customer_notes: z.string().nullable().optional(),
  configuration_version: z.string().nullable().optional(),
  last_notification_error: z.string().nullable().optional(),
  completion_message: z.string().nullable().optional(),
  cancellation_reason: z.string().nullable().optional(),
  submitted_at: z.string().nullable().optional(),
  updated_at: z.string().nullable().optional(),
  confirmed_at: z.string().nullable().optional(),
  ready_at: z.string().nullable().optional(),
  completed_at: z.string().nullable().optional(),
  cancelled_at: z.string().nullable().optional(),
  phone_normalized: z.string().nullable().optional(),
  email: z.string().nullable().optional(),
  delivery_address: z.string().nullable().optional(),
  phone_present: z.boolean().optional(),
  email_present: z.boolean().optional(),
  delivery_address_present: z.boolean().optional(),
  notes: z.array(RequestNoteSchema).optional(),
  events: z.array(RequestEventSchema).optional(),
});

export const RequestListSchema = z.object({
  items: z.array(RequestCardSchema),
  next_cursor: z.string().nullable().optional(),
  counts: z.record(z.string(), z.number()).optional(),
});

export const SetupStatusSchema = z.object({
  setup_required: z.boolean(),
  module_enabled: z.boolean().optional(),
  enabled_types: z.array(z.string()).optional(),
  capture_active: z.boolean().optional(),
});

export type RequestCard = z.infer<typeof RequestCardSchema>;
export type RequestDetail = z.infer<typeof RequestDetailSchema>;
export type RequestNote = z.infer<typeof RequestNoteSchema>;
export type RequestEvent = z.infer<typeof RequestEventSchema>;
export type SetupStatus = z.infer<typeof SetupStatusSchema>;

export type RequestsErrorKind = 'auth' | 'forbidden' | 'offline' | 'setup' | 'other';

export const STATUS_LABEL_KEYS: Record<string, StringKey> = {
  NEW: 'reqStatusNew',
  IN_REVIEW: 'reqStatusInReview',
  WAITING_FOR_CUSTOMER: 'reqStatusWaiting',
  CONFIRMED: 'reqStatusConfirmed',
  READY: 'reqStatusReady',
  COMPLETED: 'reqStatusCompleted',
  CANCELLED: 'reqStatusCancelled',
};

export const TYPE_LABEL_KEYS: Record<string, StringKey> = {
  ORDER: 'reqTypeOrder',
  APPOINTMENT: 'reqTypeAppointment',
  OTHER: 'reqTypeOther',
};

export const CHANNEL_LABEL_KEYS: Record<string, StringKey> = {
  instagram_dm: 'reqChannelInstagram',
  facebook_messenger: 'reqChannelFacebook',
  whatsapp_cloud: 'reqChannelWhatsApp',
  comment_linked_dm: 'reqChannelCommentDm',
};

export const FINAL_ACTION_BY_TYPE: Record<string, { action: string; labelKey: StringKey }> = {
  APPOINTMENT: { action: 'confirm_appointment', labelKey: 'reqActionConfirmAppointment' },
  ORDER: { action: 'mark_ready', labelKey: 'reqActionMarkReady' },
  OTHER: { action: 'complete_request', labelKey: 'reqActionComplete' },
};

export function cardSummary(card: RequestCard): string {
  if (card.request_type === 'APPOINTMENT') {
    const parts = [card.preferred_date, card.preferred_time].filter(Boolean);
    if (parts.length) return parts.join(' · ');
  }
  return (card.title || '').trim();
}

export function idempotencyKey(prefix: string): string {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
}

/** ISO bound for server-side list filter (`created_after`). */
export function createdAfterForPreset(preset: DatePreset): string | null {
  if (preset === 'all') return null;
  const startOfToday = new Date();
  startOfToday.setHours(0, 0, 0, 0);
  if (preset === 'today') return startOfToday.toISOString();
  const now = Date.now();
  if (preset === 'last7') return new Date(now - 7 * 24 * 60 * 60 * 1000).toISOString();
  if (preset === 'last30') return new Date(now - 30 * 24 * 60 * 60 * 1000).toISOString();
  return null;
}

export function formatWhen(iso: string | null | undefined, locale: string): string {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleString(
      locale.startsWith('ar') ? 'ar' : locale.startsWith('fr') ? 'fr' : 'en',
      { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' },
    );
  } catch {
    return iso;
  }
}
