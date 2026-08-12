import { z } from 'zod';

import { ApiError, apiFetch } from '../../api/client';
import { isNetworkFailure } from '../../api/networkError';
import {
  RequestDetailSchema,
  RequestListSchema,
  RequestNoteSchema,
  SetupStatusSchema,
  type RequestsErrorKind,
  type RequestDetail,
  type RequestNote,
  type SetupStatus,
} from './requestsTypes';

export type ListRequestsParams = {
  requestType?: string | null;
  status?: string | null;
  sourceChannel?: string | null;
  assignedUserId?: string | null;
  q?: string | null;
  cursor?: string | null;
  createdAfter?: string | null;
  createdOnOrBefore?: string | null;
  limit?: number;
};

export function classifyRequestsError(err: unknown): RequestsErrorKind {
  if (isNetworkFailure(err)) return 'offline';
  if (err instanceof ApiError) {
    if (err.status === 401) return 'auth';
    if (err.status === 403) return 'forbidden';
    const body = err.body as { detail?: { code?: string } | string; code?: string } | null;
    const code =
      typeof body?.detail === 'object' && body?.detail
        ? body.detail.code
        : typeof body?.code === 'string'
          ? body.code
          : null;
    if (code === 'REQUESTS_SETUP_REQUIRED' || err.status === 409) return 'setup';
  }
  return 'other';
}

export async function fetchRequestsSetupStatus(): Promise<SetupStatus> {
  return apiFetch('/api/requests/setup-status', { schema: SetupStatusSchema });
}

export async function listRequests(params: ListRequestsParams = {}) {
  const q = new URLSearchParams();
  if (params.requestType) q.set('request_type', params.requestType);
  if (params.status) q.set('status', params.status);
  if (params.sourceChannel) q.set('source_channel', params.sourceChannel);
  if (params.assignedUserId) q.set('assigned_user_id', params.assignedUserId);
  if (params.q?.trim()) q.set('q', params.q.trim());
  if (params.cursor) q.set('cursor', params.cursor);
  if (params.createdAfter) q.set('created_after', params.createdAfter);
  if (params.createdOnOrBefore) q.set('created_on_or_before', params.createdOnOrBefore);
  q.set('limit', String(params.limit ?? 25));
  const path = `/api/requests?${q.toString()}`;
  return apiFetch(path, { schema: RequestListSchema });
}

export async function getRequest(requestId: string): Promise<RequestDetail> {
  return apiFetch(`/api/requests/${encodeURIComponent(requestId)}`, {
    schema: RequestDetailSchema,
  });
}

export async function assignRequest(
  requestId: string,
  body: { assigned_user_id: string | null; row_version: number },
): Promise<RequestDetail> {
  return apiFetch(`/api/requests/${encodeURIComponent(requestId)}/assign`, {
    method: 'POST',
    body: JSON.stringify(body),
    schema: RequestDetailSchema,
  });
}

export async function addRequestNote(requestId: string, noteBody: string): Promise<RequestNote> {
  return apiFetch(`/api/requests/${encodeURIComponent(requestId)}/notes`, {
    method: 'POST',
    body: JSON.stringify({ body: noteBody }),
    schema: RequestNoteSchema,
  });
}

export async function changeRequestStatus(
  requestId: string,
  body: { to_status: string; row_version: number; cancellation_reason?: string | null },
): Promise<RequestDetail> {
  return apiFetch(`/api/requests/${encodeURIComponent(requestId)}/status`, {
    method: 'POST',
    body: JSON.stringify(body),
    schema: RequestDetailSchema,
  });
}

export async function runFinalAction(
  requestId: string,
  body: {
    action: string;
    row_version: number;
    completion_message?: string | null;
    idempotency_key: string;
    send_notification?: boolean;
  },
): Promise<RequestDetail> {
  return apiFetch(`/api/requests/${encodeURIComponent(requestId)}/final-action`, {
    method: 'POST',
    body: JSON.stringify(body),
    schema: RequestDetailSchema,
  });
}

export async function retryRequestNotify(
  requestId: string,
  idempotency_key: string,
): Promise<RequestDetail> {
  return apiFetch(`/api/requests/${encodeURIComponent(requestId)}/notify-retry`, {
    method: 'POST',
    body: JSON.stringify({ idempotency_key }),
    schema: RequestDetailSchema,
  });
}

/** Loose parse helper for tests / defensive callers. */
export function parseListPayload(raw: unknown) {
  return RequestListSchema.parse(raw);
}

export const RequestsApiSchemas = {
  list: RequestListSchema,
  detail: RequestDetailSchema,
  setup: SetupStatusSchema,
  note: RequestNoteSchema,
  z,
};
