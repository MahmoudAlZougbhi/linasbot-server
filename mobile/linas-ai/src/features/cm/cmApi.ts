import { z } from 'zod';

import { API_BASE, ApiError, apiFetch } from '../../api/client';
import { tokenStore } from '../../auth/tokenStore';
import { resolveCmEtag } from './cmEtag';

const EnvelopeSchema = z
  .object({
    success: z.literal(true),
    data: z
      .object({
        etag: z.string().optional().nullable(),
        payload: z.record(z.string(), z.unknown()).optional(),
        data: z.record(z.string(), z.unknown()).optional(),
        section: z.string().optional(),
        revision: z.number().optional(),
      })
      .passthrough(),
  })
  .passthrough();

export const CmMetaSchema = z
  .object({
    success: z.literal(true),
    sections: z.array(z.string()).optional(),
    publish_enabled: z.boolean().optional(),
    tenant_runtime: z.string().optional(),
    has_published_content: z.boolean().optional(),
    runtime_mode: z.string().optional(),
    publish_disabled_message: z.string().optional().nullable(),
  })
  .passthrough();

export type CmDraft = {
  payload: Record<string, unknown>;
  etag: string;
  revision?: number;
};

export type CmMeta = z.infer<typeof CmMetaSchema>;

async function parseJson(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) return {};
  return JSON.parse(text) as unknown;
}

async function authHeaders(extra?: HeadersInit): Promise<Headers> {
  const headers = new Headers(extra);
  headers.set('Content-Type', 'application/json');
  headers.set('Accept', 'application/json');
  const access = await tokenStore.getAccessToken();
  if (!access) {
    throw new ApiError('Not authenticated', 401, null);
  }
  headers.set('Authorization', `Bearer ${access}`);
  return headers;
}

function extractPayload(envelope: z.infer<typeof EnvelopeSchema>['data']): Record<string, unknown> {
  const raw = envelope.payload ?? envelope.data ?? {};
  return raw && typeof raw === 'object' && !Array.isArray(raw)
    ? (raw as Record<string, unknown>)
    : {};
}

export async function fetchCmMeta() {
  return apiFetch('/api/cm/meta', { schema: CmMetaSchema });
}

/** @deprecated Prefer getCmDraft — kept for any stub callers. */
export async function fetchCmDraft(section: string) {
  return apiFetch(`/api/cm/draft/${section}`, { schema: EnvelopeSchema });
}

export async function getCmDraft(section: string): Promise<CmDraft> {
  const headers = await authHeaders();
  const response = await fetch(`${API_BASE}/api/cm/draft/${section}`, { headers });
  const body = await parseJson(response);
  if (!response.ok) {
    throw new ApiError('Failed to load CM draft', response.status, body);
  }
  const parsed = EnvelopeSchema.parse(body);
  const etag = resolveCmEtag(
    parsed.data.etag,
    response.headers.get('etag') || response.headers.get('ETag'),
  );
  if (!etag) {
    throw new ApiError('CM draft missing ETag', 500, body);
  }
  return {
    payload: extractPayload(parsed.data),
    etag,
    revision: typeof parsed.data.revision === 'number' ? parsed.data.revision : undefined,
  };
}

export async function putCmDraft(
  section: string,
  payload: Record<string, unknown>,
  ifMatch: string,
): Promise<CmDraft> {
  const headers = await authHeaders({ 'If-Match': ifMatch });
  const response = await fetch(`${API_BASE}/api/cm/draft/${section}`, {
    method: 'PUT',
    headers,
    body: JSON.stringify({ payload }),
  });
  const body = await parseJson(response);
  if (response.status === 409) {
    throw new ApiError('Draft conflict — reload and retry', 409, body);
  }
  if (!response.ok) {
    const detail =
      body && typeof body === 'object' && 'detail' in body
        ? String((body as { detail: unknown }).detail)
        : 'Failed to save CM draft';
    throw new ApiError(detail, response.status, body);
  }
  const parsed = EnvelopeSchema.parse(body);
  const etag = resolveCmEtag(
    parsed.data.etag,
    response.headers.get('etag') || response.headers.get('ETag'),
    ifMatch,
  );
  return {
    payload: extractPayload(parsed.data),
    etag,
    revision: typeof parsed.data.revision === 'number' ? parsed.data.revision : undefined,
  };
}

export function asRecordList(value: unknown): Record<string, unknown>[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is Record<string, unknown> => !!item && typeof item === 'object');
}

export function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

export function newId(prefix: string): string {
  return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

export function emptyLabels(): Record<string, string> {
  return { en: '', ar: '', fr: '', franco: '' };
}

export function primaryLabel(labels: unknown): string {
  const rec = asRecord(labels);
  for (const key of ['en', 'ar', 'fr', 'franco']) {
    const v = rec[key];
    if (typeof v === 'string' && v.trim()) return v.trim();
  }
  return '';
}

export function listToText(value: unknown): string {
  return Array.isArray(value) ? value.map(String).join('\n') : '';
}

export function textToList(text: string): string[] {
  return text
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);
}
