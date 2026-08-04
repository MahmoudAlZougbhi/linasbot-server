/**
 * Shared domain types for checkJs / JSDoc (dashboard SPA).
 * Prefer narrowing unknown API payloads via src/utils/apiValidate.js before use.
 */

type JsonPrimitive = string | number | boolean | null;
type JsonValue = JsonPrimitive | JsonObject | JsonArray;
interface JsonObject {
  [key: string]: JsonValue | undefined;
}
interface JsonArray extends Array<JsonValue> {}

type SocialChannel = "whatsapp" | "instagram" | "facebook" | "web" | string;

interface AuthUser {
  id?: string;
  email: string;
  name: string;
  role: string;
  permissions?: string[] | Record<string, boolean> | null;
  resolvedPermissions?: Record<string, boolean>;
  status: string;
  lastLogin?: string | null;
  createdAt?: string | null;
  tenantId?: string;
}

interface AuthSessionData {
  user: AuthUser;
  timestamp: string;
  lastValidatedAt?: string | null;
}

interface AuthContextValue {
  user: AuthUser | null;
  loading: boolean;
  login: (email: string, password: string, redirectTo?: string, retryCount?: number) => Promise<AuthUser>;
  register: (payload: {
    businessName: string;
    email: string;
    password: string;
    name?: string;
  }) => Promise<AuthUser>;
  logout: () => Promise<void>;
  changePassword: (currentPassword: string, newPassword: string) => Promise<boolean>;
  getUsers: () => Promise<unknown>;
  createUser: (userData: Record<string, unknown>) => Promise<unknown>;
  updateUser: (userId: string, updates: Record<string, unknown>) => Promise<unknown>;
  deleteUser: (userId: string) => Promise<boolean>;
  refreshUser: () => Promise<void>;
  [key: string]: unknown;
}

interface ApiResult {
  success: boolean;
  error?: string;
  message?: string;
  [key: string]: unknown;
}

interface LiveChatFaqMatch {
  faq_id?: string;
  stored_question?: string;
  user_question?: string;
  user_language?: string;
  similarity?: number;
  tier?: string;
  [key: string]: unknown;
}

interface LiveChatFaqEntry {
  answer?: string;
  [key: string]: unknown;
}

interface LiveChatMessageMetadata {
  faq_match?: LiveChatFaqMatch | null;
  current_entry?: LiveChatFaqEntry | null;
  [key: string]: unknown;
}

interface LiveChatMessage {
  id?: string;
  message_id?: string;
  content?: string;
  text?: string;
  role?: string;
  is_user?: boolean;
  timestamp?: string;
  media_url?: string;
  media_type?: string;
  type?: string;
  handled_by?: string;
  audio_url?: string;
  image_url?: string;
  metadata?: LiveChatMessageMetadata | null;
  [key: string]: unknown;
}

interface LiveChatConversation {
  user_id: string;
  conversation_id: string;
  channel?: SocialChannel;
  status?: string;
  conversation_state?: string;
  message_count?: number;
  last_activity?: string;
  last_message?: LiveChatMessage | string | null;
  last_message_text?: string;
  user_name?: string;
  user_phone?: string;
  phone_number?: string;
  language?: string;
  gender?: string;
  sentiment?: string;
  duration_seconds?: number;
  wait_time_seconds?: number;
  is_new_customer?: boolean;
  human_takeover_active?: boolean;
  template_send_logged_at?: string;
  last_message_text?: string;
  last_message_at?: string;
  customer_name?: string;
  user_name?: string;
  phone?: string;
  user_phone?: string;
  phone_number?: string;
  operator_id?: string | null;
  unread_count?: number;
  is_new_customer?: boolean;
  sentiment?: string;
  language?: string;
  gender?: string;
  reason?: string;
  duration_seconds?: number;
  wait_time_seconds?: number;
  human_takeover_active?: boolean;
  post_release_escalation_suppressed_until?: string | null;
  is_live?: boolean;
  template_send_logged_at?: string;
  [key: string]: unknown;
}

/** Conversation enriched by the Live Chat list with derived recency fields. */
interface LiveChatListConversation extends LiveChatConversation {
  _lastTs: number;
  _isLive: boolean;
}

interface SelectedConversation {
  conversation: LiveChatConversation;
  history: LiveChatMessage[];
  [key: string]: unknown;
}

interface LiveChatMessageCacheEntry {
  messages: LiveChatMessage[];
  hasMore?: boolean;
  cachedAt?: number;
  isPartial?: boolean;
}

interface LiveChatFaqContext {
  faq_match?: LiveChatFaqMatch | null;
  current_entry?: LiveChatFaqEntry | null;
}

interface LiveChatMessageModalState {
  message: LiveChatMessage;
  feedbackType?: string;
}

interface TemplateSendFilterMeta {
  log_entries_matched?: number;
  distinct_recipients?: number;
  matched_chats?: number;
  index_scanned?: number;
}

interface RecentOperatorSessionEntry {
  cacheKey?: string;
  altKey?: string;
  ts?: number;
  messages?: LiveChatMessage[];
}

interface QueueItem {
  user_id: string;
  conversation_id: string;
  message_count?: number;
  channel?: SocialChannel;
  wait_time_seconds?: number;
  last_message?: string | LiveChatMessage | null;
  user_name?: string;
  user_phone?: string;
  reason?: string;
  sentiment?: string;
  language?: string;
  unread_count?: number;
  is_new_customer?: boolean;
  [key: string]: unknown;
}

interface RoleData {
  id: string;
  name?: string;
  permissions?: string[] | Record<string, boolean>;
  [key: string]: unknown;
}

interface DashboardUser {
  id: string;
  email: string;
  name?: string;
  role?: string;
  status?: string;
  lastLogin?: string | null;
  [key: string]: unknown;
}

interface MetricsSnapshot {
  [key: string]:
    | number
    | string
    | boolean
    | null
    | undefined
    | MetricsSnapshot
    | MetricsSnapshot[]
    | Array<number | string | MetricsSnapshot | Record<string, unknown>>;
}

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

interface FormFieldMap {
  [key: string]: string | number | boolean | null | undefined;
}

interface AxiosLikeError {
  code?: string;
  message?: string;
  name?: string;
  response?: {
    status?: number;
    data?: { message?: string; error?: string; detail?: string; [key: string]: unknown };
  };
}

interface BotStatus {
  status: string;
  uptime: number;
  responseTime: number;
  features: string[];
  currentProvider?: string;
}

interface QAFilters {
  category?: string;
  language?: string;
  query?: string;
  active_only?: boolean;
}

interface TestMessagePayload {
  phone: string;
  message: string;
  provider: string;
  channel?: "instagram" | "facebook";
}

interface PermissionsContextValue {
  permissions: Record<string, boolean>;
  roles: Record<string, RoleData>;
  hasPermission: (feature: string) => boolean;
  canManageUsers: () => boolean;
  hasAccessToPath: (path: string) => boolean;
  getFirstAccessiblePath: () => string;
  isAdmin: () => boolean;
}

interface OperatorStatusContextValue {
  operatorStatus: string;
  setOperatorStatus: import("react").Dispatch<import("react").SetStateAction<string>>;
}

interface DisplayDateTimeOptions {
  showDate?: boolean;
  showTime?: boolean;
  showSeconds?: boolean;
  dateStyle?: "short" | "medium" | "long" | "full";
  timeStyle?: "short" | "medium" | "long";
}

interface ContentFileRecord {
  id?: string;
  title: string;
  content: string;
  tags: string[];
  language?: string;
  audience?: string;
  priority?: string | number;
  [key: string]: unknown;
}

interface TrainingBackupRecord {
  filename?: string;
  created?: string;
  created_at?: string;
  size?: number;
  [key: string]: unknown;
}

interface FileStatsRecord {
  lines?: number;
  words?: number;
  sections?: number;
  characters?: number;
  file_size?: number;
  [key: string]: unknown;
}

interface DynamicMessageEntry {
  label?: string;
  when_used?: string;
  messages?: Record<string, string>;
  [key: string]: unknown;
}

interface ActivityFlowEntry {
  timestamp?: string;
  user_id?: string;
  user_phone?: string;
  user_phone_masked?: string;
  user_id_masked?: string;
  user_name?: string;
  user_gender?: string;
  customer_file_status?: string;
  source?: string;
  message_type?: string;
  user_message?: string;
  bot_to_user?: string;
  flow_error?: string;
  flow_steps?: FlowStepData[];
  customer_context_sent?: string;
  bot_sent_to_ai_full?: string;
  ai_query_summary?: string;
  model?: string;
  tokens?: number;
  prompt_tokens?: number;
  completion_tokens?: number;
  response_time_ms?: number;
  qa_match_score?: number;
  tool_calls?: string[];
  ai_raw_response?: string;
  token_source?: string;
  input_cost_usd?: number;
  output_cost_usd?: number;
  cost_usd?: number;
  [key: string]: unknown;
}

interface FlowStepData {
  step?: number;
  title?: string;
  content?: string;
  tokens?: number;
  model?: string;
  cost_usd?: number;
  event_type?: string;
  status?: string;
  duration_ms?: number;
  metadata?: Record<string, unknown>;
}

interface BranchHolidayRow {
  branchId?: string | number | null;
  startDate?: string;
  endDate?: string;
  labelAr?: string;
  labelEn?: string;
  greetingAr?: string;
  greetingEn?: string;
  blockBooking?: boolean;
}

interface IntegrationStatus {
  name: string;
  service?: string;
  configured?: boolean;
  notes?: string;
}

interface MetaAppPublicStatus {
  key: string;
  app_id: string;
  classification: "own_business" | "tech_provider";
  oauth_configured?: boolean;
  advanced_access_approved?: boolean;
  credentials_configured?: boolean;
  enabled?: boolean;
}

interface MetaConnectionStatus {
  binding_id: string;
  tenant_id: string;
  channel: "facebook" | "instagram";
  asset_id: string;
  app_key: string;
  status: "active" | "inactive" | "testing" | "disconnected";
  generation: number;
  token_status?: "valid" | "expired" | "unavailable";
  expires_at?: number | null;
  granted_permissions?: string[];
}

interface TrainingQAPair {
  id: string;
  question: string;
  answer: string;
  category?: string;
  language?: string;
  timestamp?: string;
}

interface TrainingStatistics {
  total: number;
  by_language: Record<string, number>;
  by_category: Record<string, number>;
}

interface TestingChatMessage {
  id: string;
  role: string;
  type: string;
  content: string;
  timestamp: string;
  success?: boolean;
}

interface TestingLabSession {
  messages: TestingChatMessage[];
  turns: TestingTestResult[];
}

interface TestingTestResult {
  id: number;
  type: string;
  input?: string;
  language?: string;
  output?: string;
  responseTime?: number;
  timestamp?: string;
  success?: boolean;
  mode?: string;
  userType?: string;
  userPhone?: string;
  provider?: string;
  channel?: string;
  metadata?: Record<string, unknown>;
  [key: string]: unknown;
}

interface ApiEndpointDefinition {
  id: string;
  name: string;
  method: string;
  endpoint: string;
  params?: Record<string, string | number>;
  body?: Record<string, unknown>;
  requiresAuth?: boolean;
}

interface ApiTestResult {
  id: number;
  endpoint: string;
  method: string;
  url: string;
  status: number;
  success: boolean;
  data: unknown;
  responseTime: number;
  timestamp: string;
}

interface DebugLogEntry {
  message: string;
  type: string;
  timestamp: string;
}

interface SettingsFormState {
  botName: string;
  defaultLanguage: string;
  responseTimeout: number;
  enableVoice: boolean;
  enableImages: boolean;
  enableTraining: boolean;
  notificationsEnabled: boolean;
  emailAlerts: boolean;
  humanTakeoverNotifyMobiles: string;
}
