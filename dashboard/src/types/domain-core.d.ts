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
  logout: () => Promise<void>;
  changePassword: (currentPassword: string, newPassword: string) => Promise<boolean>;
  refreshUser: () => Promise<void>;
  [key: string]: unknown;
}

interface ApiResult {
  success: boolean;
  error?: string;
  message?: string;
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
