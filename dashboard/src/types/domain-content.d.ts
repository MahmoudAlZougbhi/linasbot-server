/**
 * Content / Meta / training / settings domain types (LOC split from domain.d.ts).
 */

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
  cost_status?: "estimated" | "unavailable" | "none" | "actual" | string;
  cost_basis?: string;
  channel?: string;
  direction?: string;
  conversation_id?: string;
  message_id?: string;
  handler_path?: string;
  outcome?: string;
  pipeline_decisions?: Array<Record<string, unknown>>;
  cm_diagnostics?: {
    reason?: string | null;
    content_version_id?: string | null;
    index_version_id?: string | null;
    source_ids?: string[];
    retrieved_sources?: Array<{ source_id?: string; title?: string }>;
    validated?: boolean | null;
    regenerated?: boolean | null;
    failed_rules?: string[];
  } | null;
  faq_match?: {
    faq_id?: string | number | null;
    tier?: string | null;
    similarity?: number | null;
    stored_language?: string | null;
  } | null;
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
  asset_id_masked?: string;
  page_id?: string;
  page_id_masked?: string;
  instagram_account_id?: string;
  instagram_account_id_masked?: string;
  page_name?: string;
  instagram_username?: string;
  app_key: string;
  app_label?: string;
  status: "active" | "inactive" | "testing" | "disconnected";
  generation: number;
  token_status?: "valid" | "expired" | "unavailable";
  expires_at?: number | null;
  granted_permissions?: string[];
  connected_at?: number;
  created_at?: number;
  updated_at?: number;
  authorized_meta_user_id_hash?: string;
  superseded_by_binding_id?: string;
  asset_key?: string;
  auth_flow?: "facebook_login" | "instagram_login";
  webhook_subscription?: {
    status?: string;
    subscribed_fields?: string[];
    error?: string;
    checked_at?: number;
    ready_for_dm?: boolean;
  };
  declined_permissions?: string[];
  comment_replies?: {
    enabled: boolean;
    instructions?: string;
    scopes_ready?: boolean;
    scopes_required?: string[];
    scopes_granted?: string[];
    updated_at?: number;
  };
}

interface MetaAuthorizationGroup {
  authorized_meta_user_id_hash: string;
  app_key?: string;
  app_label?: string;
  authorization_title?: string;
  assets: MetaConnectionStatus[];
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
