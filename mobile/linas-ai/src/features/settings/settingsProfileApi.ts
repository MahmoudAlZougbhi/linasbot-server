import { z } from 'zod';

import { ApiError, apiFetch } from '../../api/client';
import { tokenStore } from '../../auth/tokenStore';

const OwnerProfileSchema = z
  .object({
    success: z.literal(true),
    profile: z
      .object({
        email: z.string().nullable().optional(),
        display_name: z.string().nullable().optional(),
      })
      .passthrough(),
  })
  .passthrough();

const EmailChangeSchema = z
  .object({
    success: z.boolean(),
    message: z.string().optional(),
    error: z.string().optional(),
  })
  .passthrough();

export type OwnerSettingsProfile = {
  email: string;
  displayName: string;
};

export function settingsApiErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError && err.body && typeof err.body === 'object') {
    const error = (err.body as { error?: unknown }).error;
    if (typeof error === 'string' && error.trim()) return error;
  }
  return fallback;
}

/** GET /api/owner-ai/profile — display name + email for Settings rows. */
export async function fetchOwnerSettingsProfile(): Promise<OwnerSettingsProfile> {
  const body = await apiFetch('/api/owner-ai/profile', {
    method: 'GET',
    schema: OwnerProfileSchema,
  });
  return {
    email: String(body.profile.email || '').trim(),
    displayName: String(body.profile.display_name || '').trim(),
  };
}

/** PATCH /api/owner-ai/profile — persist display_name (existing owner profile API). */
export async function patchOwnerDisplayName(displayName: string): Promise<OwnerSettingsProfile> {
  const cleaned = displayName.trim().slice(0, 80);
  const body = await apiFetch('/api/owner-ai/profile', {
    method: 'PATCH',
    body: JSON.stringify({ display_name: cleaned }),
    schema: OwnerProfileSchema,
  });
  const next: OwnerSettingsProfile = {
    email: String(body.profile.email || '').trim(),
    displayName: String(body.profile.display_name || cleaned).trim(),
  };
  const stored = await tokenStore.getUser();
  if (stored) {
    await tokenStore.setUser({ ...stored, name: next.displayName, displayName: next.displayName });
  }
  return next;
}

/** POST /api/auth/request-email-change — confirm link is emailed to the new address. */
export async function requestOwnerEmailChange(
  newEmail: string,
  currentPassword: string,
): Promise<string> {
  const body = await apiFetch('/api/auth/request-email-change', {
    method: 'POST',
    body: JSON.stringify({
      new_email: newEmail.trim().toLowerCase(),
      current_password: currentPassword,
    }),
    schema: EmailChangeSchema,
  });
  if (!body.success) {
    throw new ApiError(body.error || 'Email change failed', 400, body);
  }
  return body.message || '';
}
