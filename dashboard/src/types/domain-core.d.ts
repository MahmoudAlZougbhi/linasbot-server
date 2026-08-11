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
  emailVerified?: boolean;
  businessName?: string;
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

