import { z } from 'zod';

import { API_BASE } from '../config';
import { ChatMessageSchema } from './types';
import { ApiError } from './client';

const GuestSessionSchema = z.object({
  id: z.string(),
  limit_reached: z.boolean(),
  max_input_tokens: z.number().optional(),
  messages: z.array(ChatMessageSchema),
});

const EnsureSchema = z.object({
  success: z.literal(true),
  session: GuestSessionSchema,
});

const SendOkSchema = z.object({
  success: z.literal(true),
  message: ChatMessageSchema,
  session: GuestSessionSchema,
  meta: z
    .object({
      tools_used: z.array(z.unknown()).optional(),
      language: z.string().optional(),
    })
    .optional(),
});

const SendGateSchema = z.object({
  success: z.literal(false),
  error: z.string(),
  code: z.literal('GUEST_QUESTION_LIMIT'),
  session: GuestSessionSchema,
  message: z.record(z.string(), z.string()).optional(),
});

export type GuestSession = z.infer<typeof GuestSessionSchema>;

async function parseJson(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) return {};
  return JSON.parse(text) as unknown;
}

function detailCode(body: unknown): string | null {
  if (!body || typeof body !== 'object') return null;
  const detail = (body as { detail?: unknown }).detail;
  if (!detail || typeof detail !== 'object') return null;
  const code = (detail as { code?: unknown; error?: unknown }).code;
  const error = (detail as { error?: unknown }).error;
  if (typeof code === 'string') return code;
  if (typeof error === 'string') return error;
  return null;
}

export async function ensureGuestSession(guestSessionId: string, language?: string) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 12000);
  try {
    const response = await fetch(`${API_BASE}/api/guest-ai/session`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        ...(language ? { 'Accept-Language': language } : {}),
      },
      body: JSON.stringify({ guest_session_id: guestSessionId, language }),
      signal: ctrl.signal,
    });
    const body = await parseJson(response);
    if (!response.ok) {
      throw new ApiError('Guest session failed', response.status, body);
    }
    const parsed = EnsureSchema.safeParse(body);
    if (parsed.success) return parsed.data.session;
    const loose = looseGuestSession(body);
    if (loose) return loose;
    throw new ApiError('Guest session failed', response.status, body);
  } finally {
    clearTimeout(timer);
  }
}

function looseGuestSession(body: unknown): GuestSession | null {
  if (!body || typeof body !== 'object') return null;
  const session = (body as { session?: unknown }).session;
  if (!session || typeof session !== 'object') return null;
  const row = session as { id?: unknown; messages?: unknown; limit_reached?: unknown };
  if (typeof row.id !== 'string') return null;
  const messages = Array.isArray(row.messages) ? row.messages : [];
  const clean = messages.flatMap((item) => {
    if (!item || typeof item !== 'object') return [];
    const msg = item as { id?: unknown; role?: unknown; content?: unknown; created_at?: unknown };
    const role = msg.role === 'user' || msg.role === 'system' ? msg.role : 'assistant';
    const created = typeof msg.created_at === 'number' ? msg.created_at : 0;
    if (typeof msg.content !== 'string') return [];
    return [{ id: String(msg.id ?? ''), role, content: msg.content, created_at: created }];
  });
  return {
    id: row.id,
    limit_reached: row.limit_reached === true,
    messages: clean,
  };
}

export async function sendGuestMessage(
  guestSessionId: string,
  content: string,
  language?: string,
): Promise<{ ok: true; session: GuestSession; message: z.infer<typeof ChatMessageSchema> } | {
  ok: false;
  session: GuestSession;
  gateMessages?: Record<string, string>;
}> {
  const response = await fetch(`${API_BASE}/api/guest-ai/session/messages`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
      ...(language ? { 'Accept-Language': language } : {}),
    },
    body: JSON.stringify({ guest_session_id: guestSessionId, content, language }),
  });
  const body = await parseJson(response);
  if (response.status === 400) {
    const code = detailCode(body);
    throw new ApiError(code || 'Guest message rejected', 400, body);
  }
  if (!response.ok) {
    throw new ApiError('Guest message failed', response.status, body);
  }
  const gated = SendGateSchema.safeParse(body);
  if (gated.success) {
    return { ok: false, session: gated.data.session, gateMessages: gated.data.message };
  }
  const ok = SendOkSchema.parse(body);
  return { ok: true, session: ok.session, message: ok.message };
}
