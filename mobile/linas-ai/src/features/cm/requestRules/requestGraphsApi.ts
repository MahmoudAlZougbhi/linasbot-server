import { z } from 'zod';

import { apiFetch } from '../../../api/client';
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

export async function listRequestGraphs(): Promise<RequestGraphRow[]> {
  const data = await apiFetch('/api/cm/request-graphs', { schema: ListSchema });
  return (data.graphs || []).map(parseGraphRow);
}

export async function previewRequestGraph(body: {
  title: string;
  source_text: string;
  destination: string;
}): Promise<RequestGraphRow> {
  const data = await apiFetch('/api/cm/request-graphs/preview', {
    method: 'POST',
    schema: PreviewSchema,
    body: JSON.stringify(body),
  });
  return parseGraphRow({ ...(data.preview || {}), title: body.title, destination: body.destination });
}

export async function publishRequestGraph(body: {
  source_item_id: string;
  title: string;
  source_text: string;
  destination: string;
  confirm: boolean;
}): Promise<RequestGraphRow> {
  const data = await apiFetch('/api/cm/request-graphs/publish', {
    method: 'POST',
    schema: PublishSchema,
    body: JSON.stringify(body),
  });
  return parseGraphRow({ ...(data.graph || {}), source_item_id: body.source_item_id });
}

export async function deleteRequestGraph(definitionId: string): Promise<void> {
  await apiFetch('/api/cm/request-graphs/delete', {
    method: 'POST',
    schema: DeleteSchema,
    body: JSON.stringify({ definition_id: definitionId }),
  });
}
