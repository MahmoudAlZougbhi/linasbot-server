/**
 * Smart messaging domain types (LOC split from domain.d.ts).
 */

interface SmartMessageTemplate {
  id: string;
  name?: string;
  description?: string;
  ar?: string;
  en?: string;
  fr?: string;
  [key: string]: unknown;
}

interface SmartQueueMessageTemplateData {
  appointment_date?: string;
  [key: string]: unknown;
}

interface SmartQueueMessage {
  message_id?: string;
  content_preview?: string;
  full_content?: string;
  send_at?: string;
  sent_at?: string;
  created_at?: string;
  scheduled_at?: string;
  scheduled_for?: string;
  message_type?: string;
  status?: string;
  customer_name?: string;
  customer_phone?: string;
  reason?: string;
  details?: string;
  language?: string;
  date?: string;
  time?: string;
  time_until_send?: string;
  template_data?: SmartQueueMessageTemplateData;
  [key: string]: unknown;
}

/** Message shown/edited in the "View message" modal. */
interface SmartViewingMessage extends SmartQueueMessage {
  fullContent?: string;
}

/** Message shown/edited in the "Edit scheduled message" modal. */
interface SmartEditingScheduledMessage extends SmartQueueMessage {
  editedContent: string;
  editedSendTime: string;
}

/** Editable copy of a template loaded into the edit-template modal. */
interface SmartEditingTemplate {
  id: string;
  name: string;
  description: string;
  ar: string;
  en: string;
  fr: string;
}

/** Per-service enable/disable map for message templates. */
interface SmartServiceMapping {
  templates?: Record<string, boolean>;
  [key: string]: unknown;
}

/** Per-template daily-job schedule configuration. */
interface SmartTemplateScheduleConfig {
  enabled?: boolean;
  sendTime?: string;
  timezone?: string;
  delayHours?: number;
  [key: string]: unknown;
}

interface SmartMessagingService {
  service_id: number;
  service_name?: string;
  [key: string]: unknown;
}

interface SmartMessagingTemplateOption {
  id: string;
  name?: string;
  [key: string]: unknown;
}

interface SmartPausedCampaignRecipient {
  phone?: string;
  customer_name?: string;
  appointment_date?: string;
  appointment_time?: string;
  service_name?: string;
  branch_name?: string;
  appointment_id?: string | number;
  machine_name?: string;
  [key: string]: unknown;
}

interface SmartLeadCampaignRecipient {
  phone?: string;
  customer_name?: string;
  last_chat_date?: string;
  message_count?: number;
  last_message_preview?: string;
  [key: string]: unknown;
}

interface SmartSessionStarRating {
  user_id?: string;
  timestamp?: string;
  stars?: number;
  raw_reply?: string;
  appointment_id?: string | number;
  conversation_id?: string;
  [key: string]: unknown;
}

interface SmartTestLangPreview {
  success?: boolean;
  language?: string;
  language_source?: string;
  normalized_phone?: string;
  [key: string]: unknown;
}

interface SmartSchedulerStatistics {
  sent_today?: number;
  sent_this_week?: number;
  sent_this_month?: number;
  by_type?: Record<string, { sent?: number; [key: string]: unknown }>;
  [key: string]: unknown;
}

interface SmartSchedulerStatus {
  success?: boolean;
  scheduler_running?: boolean;
  statistics?: SmartSchedulerStatistics;
  [key: string]: unknown;
}

interface SmartCategoryCustomerRow {
  appointment_id?: string | number;
  phone?: string;
  customer_name?: string;
  reason?: string;
  type?: string;
  action_state?: string;
  date?: string;
  time?: string;
  details?: string;
  [key: string]: unknown;
}

