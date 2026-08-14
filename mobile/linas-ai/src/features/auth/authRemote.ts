import { z } from 'zod';

import { apiFetch } from '../../api/client';

const AuthResultSchema = z
  .object({
    success: z.boolean(),
    error: z.string().optional(),
    message: z.string().optional(),
  })
  .passthrough();

export type AuthResult = z.infer<typeof AuthResultSchema>;

const RegisterSchema = AuthResultSchema;

export async function registerAccount(body: {
  email: string;
  password: string;
  businessName: string;
  gender?: 'male' | 'female' | 'unset';
  preferredLanguage: string;
}): Promise<AuthResult> {
  return apiFetch('/api/auth/register', {
    method: 'POST',
    auth: false,
    body: JSON.stringify({
      email: body.email,
      password: body.password,
      business_name: body.businessName,
      gender: body.gender ?? 'unset',
      preferred_language: body.preferredLanguage,
    }),
    schema: RegisterSchema,
  });
}

export async function verifyEmailCode(email: string, code: string): Promise<AuthResult> {
  return apiFetch('/api/auth/verify-email', {
    method: 'POST',
    auth: false,
    body: JSON.stringify({ token: code, email }),
    schema: AuthResultSchema,
  });
}

export async function resendVerification(email: string): Promise<AuthResult> {
  return apiFetch('/api/auth/resend-verification', {
    method: 'POST',
    auth: false,
    body: JSON.stringify({ email }),
    schema: AuthResultSchema,
  });
}

export async function requestPasswordReset(email: string): Promise<AuthResult> {
  return apiFetch('/api/auth/forgot-password', {
    method: 'POST',
    auth: false,
    body: JSON.stringify({ email }),
    schema: AuthResultSchema,
  });
}

export async function resetPasswordWithCode(
  email: string,
  code: string,
  newPassword: string,
): Promise<AuthResult> {
  return apiFetch('/api/auth/reset-password', {
    method: 'POST',
    auth: false,
    body: JSON.stringify({ token: code, email, new_password: newPassword }),
    schema: AuthResultSchema,
  });
}

export async function patchOwnerGender(gender: 'male' | 'female' | 'unset'): Promise<void> {
  await apiFetch('/api/owner-ai/profile', {
    method: 'PATCH',
    body: JSON.stringify({ gender }),
    schema: z.object({ success: z.literal(true) }).passthrough(),
  });
}
