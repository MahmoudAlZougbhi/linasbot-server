import { z } from 'zod';

import { ApiError, apiFetch } from '../../api/client';

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
  users: z.array(TeamUserSchema).optional(),
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
    return data.users ?? [];
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
