import { z } from 'zod';

import { API_BASE } from '../config';
import { tokenStore } from '../auth/tokenStore';
import { MobileLoginResponseSchema } from './types';

export { API_BASE };

async function parseJson(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) {
    return {};
  }
  return JSON.parse(text) as unknown;
}

export class ApiError extends Error {
  readonly status: number;
  readonly body: unknown;

  constructor(message: string, status: number, body: unknown) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

async function refreshAccessToken(): Promise<string | null> {
  const refresh = await tokenStore.getRefreshToken();
  if (!refresh) {
    return null;
  }
  const response = await fetch(`${API_BASE}/api/auth/mobile/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refresh }),
  });
  const body = await parseJson(response);
  if (!response.ok) {
    await tokenStore.clear();
    return null;
  }
  const parsed = MobileLoginResponseSchema.parse(body);
  await tokenStore.setTokens(parsed.access_token, parsed.refresh_token);
  return parsed.access_token;
}

async function authorizeHeaders(headers: Headers): Promise<void> {
  let access = await tokenStore.getAccessToken();
  if (!access) {
    access = await refreshAccessToken();
  }
  if (!access) {
    throw new ApiError('Not authenticated', 401, null);
  }
  headers.set('Authorization', `Bearer ${access}`);
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit & { schema: z.ZodType<T>; auth?: boolean },
): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set('Content-Type', 'application/json');
  headers.set('Accept', 'application/json');

  if (options.auth !== false) {
    await authorizeHeaders(headers);
  }

  let response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (response.status === 401 && options.auth !== false) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      headers.set('Authorization', `Bearer ${refreshed}`);
      response = await fetch(`${API_BASE}${path}`, { ...options, headers });
    }
  }

  const body = await parseJson(response);
  if (!response.ok) {
    throw new ApiError('Request failed', response.status, body);
  }
  return options.schema.parse(body);
}

/** Multipart upload with bearer auth + refresh. Do not set Content-Type (boundary). */
export async function apiUpload(
  path: string,
  formOrFactory: FormData | (() => FormData),
): Promise<Response> {
  const build = typeof formOrFactory === 'function' ? formOrFactory : () => formOrFactory;
  const headers = new Headers({ Accept: 'application/json' });
  await authorizeHeaders(headers);

  let response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers,
    body: build(),
  });
  if (response.status === 401) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      headers.set('Authorization', `Bearer ${refreshed}`);
      response = await fetch(`${API_BASE}${path}`, {
        method: 'POST',
        headers,
        body: build(),
      });
    }
  }
  return response;
}

export async function mobileLogin(email: string, password: string) {
  const result = await apiFetch('/api/auth/mobile/login', {
    method: 'POST',
    auth: false,
    body: JSON.stringify({ email, password }),
    schema: MobileLoginResponseSchema,
  });
  await tokenStore.setTokens(result.access_token, result.refresh_token);
  await tokenStore.setUser(result.user);
  return result;
}
