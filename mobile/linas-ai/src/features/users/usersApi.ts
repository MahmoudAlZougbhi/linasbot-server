import { z } from 'zod';

import { ApiError, apiFetch } from '../../api/client';

function asTrimmedString(value: unknown, fallback = ''): string {
  if (typeof value === 'string') return value.trim();
  if (value == null) return fallback;
  return String(value).trim() || fallback;
}

function coercePermissions(raw: unknown): Record<string, boolean> | null {
  if (raw == null) return null;
  if (typeof raw !== 'object' || Array.isArray(raw)) return null;
  const out: Record<string, boolean> = {};
  for (const [key, value] of Object.entries(raw as Record<string, unknown>)) {
    if (typeof value === 'boolean') out[key] = value;
    else if (value === 1 || value === '1' || value === 'true') out[key] = true;
    else if (value === 0 || value === '0' || value === 'false') out[key] = false;
  }
  return out;
}

/** One bad legacy row must not wipe the whole tenant list (Zod .parse on array). */
function parseTeamUser(raw: unknown): TeamUser | null {
  if (!raw || typeof raw !== 'object') return null;
  const row = raw as Record<string, unknown>;
  const id = asTrimmedString(row.id);
  if (!id) return null;
  const email = asTrimmedString(row.email);
  const role = asTrimmedString(row.role, 'viewer');
  return {
    id,
    email,
    name: row.name == null ? null : asTrimmedString(row.name) || null,
    role,
    permissions: coercePermissions(row.permissions),
    tenantId: row.tenantId == null ? undefined : asTrimmedString(row.tenantId) || undefined,
    status: row.status == null ? null : asTrimmedString(row.status) || null,
    lastLogin: row.lastLogin == null ? null : asTrimmedString(row.lastLogin) || null,
    createdAt: row.createdAt == null ? null : asTrimmedString(row.createdAt) || null,
    updatedAt: row.updatedAt == null ? null : asTrimmedString(row.updatedAt) || null,
    emailVerified: typeof row.emailVerified === 'boolean' ? row.emailVerified : undefined,
    displayName: row.displayName == null ? null : asTrimmedString(row.displayName) || null,
  };
}

const TeamUserSchema = z.object({
  id: z.string(),
  email: z.string(),
  name: z.string().nullable().optional(),
  role: z.string(),
  permissions: z.record(z.string(), z.boolean()).nullable().optional(),
  tenantId: z.string().optional(),
  status: z.string().nullable().optional(),
  lastLogin: z.string().nullable().optional(),
  createdAt: z.string().nullable().optional(),
  updatedAt: z.string().nullable().optional(),
  emailVerified: z.boolean().optional(),
  displayName: z.string().nullable().optional(),
});

const ListUsersSchema = z.object({
  success: z.boolean(),
  users: z.array(z.unknown()).optional(),
  error: z.string().optional(),
});

const MutateUserSchema = z.object({
  success: z.boolean(),
  user: TeamUserSchema.optional(),
  message: z.string().optional(),
  error: z.string().optional(),
});

const DeleteUserSchema = z.object({
  success: z.boolean(),
  message: z.string().optional(),
  error: z.string().optional(),
});

export type TeamUser = z.infer<typeof TeamUserSchema>;

export type CreateUserInput = {
  email: string;
  password: string;
  name: string;
  role: string;
  status: string;
  permissions: Record<string, boolean> | null;
};

export type UpdateUserInput = {
  name?: string;
  role?: string;
  status?: string;
  password?: string;
  permissions?: Record<string, boolean> | null;
};

export type UsersErrorKind = 'auth' | 'forbidden' | 'other';

function bodyError(body: unknown): string | null {
  if (!body || typeof body !== 'object') return null;
  const record = body as { error?: unknown; detail?: unknown; message?: unknown };
  if (typeof record.error === 'string' && record.error.trim()) return record.error;
  if (typeof record.detail === 'string' && record.detail.trim()) return record.detail;
  if (typeof record.message === 'string' && record.message.trim()) return record.message;
  return null;
}

export function classifyUsersError(err: unknown): UsersErrorKind {
  if (err instanceof ApiError) {
    if (err.status === 401) return 'auth';
    if (err.status === 403) return 'forbidden';
  }
  if (err instanceof Error) {
    const msg = err.message.toLowerCase();
    if (msg.includes('not authenticated') || msg.includes('401')) return 'auth';
    if (msg.includes('forbidden') || msg.includes('permission')) return 'forbidden';
  }
  return 'other';
}

export function usersErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    const fromBody = bodyError(err.body);
    if (fromBody) return fromBody;
    if (err.status === 403) return 'You do not have permission to manage users.';
    if (err.status === 401) return 'Not authenticated.';
  }
  if (err instanceof Error && err.message) return err.message;
  return fallback;
}

export async function listUsers(): Promise<TeamUser[]> {
  try {
    const data = await apiFetch('/api/auth/users', { schema: ListUsersSchema });
    if (!data.success) {
      throw new Error(data.error || 'Failed to fetch users');
    }
    const users: TeamUser[] = [];
    for (const row of data.users ?? []) {
      const parsed = parseTeamUser(row);
      if (parsed) users.push(parsed);
    }
    return users;
  } catch (err) {
    if (err instanceof ApiError) throw err;
    throw new Error(usersErrorMessage(err, 'Could not load users.'));
  }
}

export async function createUser(input: CreateUserInput): Promise<TeamUser> {
  try {
    const data = await apiFetch('/api/auth/users', {
      method: 'POST',
      body: JSON.stringify({
        email: input.email,
        password: input.password,
        name: input.name,
        role: input.role,
        status: input.status,
        permissions: input.permissions,
      }),
      schema: MutateUserSchema,
    });
    if (!data.success || !data.user) {
      throw new Error(data.error || 'Failed to create user');
    }
    return data.user;
  } catch (err) {
    if (err instanceof ApiError) throw err;
    throw new Error(usersErrorMessage(err, 'Could not create user.'));
  }
}

export async function updateUser(userId: string, input: UpdateUserInput): Promise<TeamUser> {
  try {
    const data = await apiFetch(`/api/auth/users/${encodeURIComponent(userId)}`, {
      method: 'PUT',
      body: JSON.stringify(input),
      schema: MutateUserSchema,
    });
    if (!data.success || !data.user) {
      throw new Error(data.error || 'Failed to update user');
    }
    return data.user;
  } catch (err) {
    if (err instanceof ApiError) throw err;
    throw new Error(usersErrorMessage(err, 'Could not update user.'));
  }
}

export async function deleteUser(userId: string): Promise<void> {
  try {
    const data = await apiFetch(`/api/auth/users/${encodeURIComponent(userId)}`, {
      method: 'DELETE',
      schema: DeleteUserSchema,
    });
    if (!data.success) {
      throw new Error(data.error || 'Failed to delete user');
    }
  } catch (err) {
    if (err instanceof ApiError) throw err;
    throw new Error(usersErrorMessage(err, 'Could not delete user.'));
  }
}
