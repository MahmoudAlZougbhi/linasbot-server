import { z } from 'zod';

import { ApiError, apiFetch } from '../../api/client';

import { usersErrorMessage } from './usersApi';
import type { PermissionMap } from './usersPermissions';

const RoleSchema = z.object({
  id: z.string(),
  name: z.string(),
  system: z.boolean(),
  permissions: z.record(z.string(), z.boolean()),
});

const ListRolesSchema = z.object({
  success: z.boolean(),
  roles: z.array(RoleSchema).optional(),
  error: z.string().optional(),
});

const MutateRoleSchema = z.object({
  success: z.boolean(),
  role: RoleSchema.optional(),
  error: z.string().optional(),
});

export type TenantRole = z.infer<typeof RoleSchema>;

export async function listRoles(): Promise<TenantRole[]> {
  try {
    const data = await apiFetch('/api/auth/users/roles', { schema: ListRolesSchema });
    if (!data.success) {
      throw new Error(data.error || 'Failed to fetch roles');
    }
    return data.roles ?? [];
  } catch (err) {
    if (err instanceof ApiError) throw err;
    throw new Error(usersErrorMessage(err, 'Could not load roles.'));
  }
}

export async function createRole(input: {
  name: string;
  permissions: PermissionMap;
}): Promise<TenantRole> {
  try {
    const data = await apiFetch('/api/auth/users/roles', {
      method: 'POST',
      body: JSON.stringify({
        name: input.name,
        permissions: input.permissions,
      }),
      schema: MutateRoleSchema,
    });
    if (!data.success || !data.role) {
      throw new Error(data.error || 'Failed to create role');
    }
    return data.role;
  } catch (err) {
    if (err instanceof ApiError) throw err;
    throw new Error(usersErrorMessage(err, 'Could not create role.'));
  }
}
