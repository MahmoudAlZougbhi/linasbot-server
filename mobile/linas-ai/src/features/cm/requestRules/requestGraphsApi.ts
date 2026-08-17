import { z } from 'zod';

import { ApiError, apiFetch } from '../../../api/client';
import { parseGraphRow, type RequestGraphRow } from './requestRuleModel';

const PreviewSchema = z
  .object({
    success: z.boolean(),
    preview: z.record(z.string(), z.unknown()).optional(),
  })
  .passthrough();

const PublishSchema = z
  .object({
    success: z.boolean(),
    graph: z.record(z.string(), z.unknown()).optional(),
  })
  .passthrough();

const ListSchema = z
  .object({
    success: z.boolean(),
    graphs: z.array(z.record(z.string(), z.unknown())).optional(),
  })
  .passthrough();

const DeleteSchema = z.object({ success: z.boolean() }).passthrough();

export type RequestGraphsErrorCode =
  | 'REQUEST_GRAPHS_UNMIGRATED'
  | 'REQUEST_GRAPHS_DB_UNAVAILABLE'
  | 'REQUEST_GRAPH_PREVIEW_FAILED'
  | 'REQUEST_GRAPH_PUBLISH_FAILED'
  | 'REQUEST_GRAPH_LOAD_FAILED';

export class RequestGraphsApiError extends Error {
  readonly code: RequestGraphsErrorCode;
  readonly status: number;

  constructor(code: RequestGraphsErrorCode, message: string, status = 0) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

function detailRecord(body: unknown): Record<string, unknown> | null {
  if (!body || typeof body !== 'object') return null;
  const rec = body as Record<string, unknown>;
  if (rec.detail && typeof rec.detail === 'object' && !Array.isArray(rec.detail)) {
    return rec.detail as Record<string, unknown>;
  }
  return rec;
}

function raiseApiError(err: unknown, fallback: RequestGraphsErrorCode): never {
  if (err instanceof RequestGraphsApiError) throw err;
  if (err instanceof ApiError) {
    const detail = detailRecord(err.body);
    const codeRaw = String(detail?.code || '').trim();
    if (codeRaw === 'REQUEST_GRAPHS_UNMIGRATED' || codeRaw === 'REQUEST_GRAPHS_DB_UNAVAILABLE') {
      throw new RequestGraphsApiError(codeRaw, String(detail?.message || err.message), err.status);
    }
    throw new RequestGraphsApiError(fallback, String(detail?.message || err.message), err.status);
  }
  throw new RequestGraphsApiError(fallback, err instanceof Error ? err.message : 'request_graphs_failed');
}

export async function listRequestGraphs(): Promise<RequestGraphRow[]> {
  try {
    const data = await apiFetch('/api/cm/request-graphs', { schema: ListSchema });
    return (data.graphs || []).map(parseGraphRow);
  } catch (err) {
    raiseApiError(err, 'REQUEST_GRAPH_LOAD_FAILED');
  }
}

export async function previewRequestGraph(body: {
  title: string;
  source_text: string;
  destination: string;
}): Promise<RequestGraphRow> {
  try {
    const data = await apiFetch('/api/cm/request-graphs/preview', {
      method: 'POST',
      schema: PreviewSchema,
      body: JSON.stringify(body),
    });
    return parseGraphRow({ ...(data.preview || {}), title: body.title, destination: body.destination });
  } catch (err) {
    raiseApiError(err, 'REQUEST_GRAPH_PREVIEW_FAILED');
  }
}

export async function publishRequestGraph(body: {
  source_item_id: string;
  title: string;
  source_text: string;
  destination: string;
  confirm: boolean;
}): Promise<RequestGraphRow> {
  try {
    const data = await apiFetch('/api/cm/request-graphs/publish', {
      method: 'POST',
      schema: PublishSchema,
      body: JSON.stringify(body),
    });
    return parseGraphRow({ ...(data.graph || {}), source_item_id: body.source_item_id });
  } catch (err) {
    raiseApiError(err, 'REQUEST_GRAPH_PUBLISH_FAILED');
  }
}

export async function deleteRequestGraph(definitionId: string): Promise<void> {
  try {
    await apiFetch('/api/cm/request-graphs/delete', {
      method: 'POST',
      schema: DeleteSchema,
      body: JSON.stringify({ definition_id: definitionId }),
    });
  } catch (err) {
    raiseApiError(err, 'REQUEST_GRAPH_PUBLISH_FAILED');
  }
}
