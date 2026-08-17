/** Upload CM article media (case examples) for knowledge/care drafts. */

import { z } from 'zod';

import { ApiError, apiUpload } from '../../api/client';
import { appendLocalFile, prepareUploadUri } from '../../api/formDataFile';

export const CmMediaUploadSchema = z
  .object({
    success: z.literal(true),
    media_id: z.string(),
    filename: z.string().optional(),
    mime: z.string().optional(),
    kind: z.enum(['image', 'video', 'file']).optional(),
    size: z.number().optional(),
  })
  .passthrough();

export type CmMediaUploadResult = z.infer<typeof CmMediaUploadSchema>;

export function parseCmMediaUploadBody(body: unknown): CmMediaUploadResult {
  return CmMediaUploadSchema.parse(body);
}

export async function uploadCmArticleMedia(file: {
  uri: string;
  name: string;
  mimeType: string;
}): Promise<CmMediaUploadResult> {
  const uploadUri = await prepareUploadUri(file.uri, file.name);
  const response = await apiUpload('/api/cm/media', () => {
    const form = new FormData();
    // Expo 57 global fetch rejects RN `{uri,name,type}` FormData parts.
    appendLocalFile(form, 'file', uploadUri, { name: file.name });
    return form;
  });
  const text = await response.text();
  let body: unknown = {};
  if (text) {
    try {
      body = JSON.parse(text) as unknown;
    } catch {
      body = { raw: text };
    }
  }
  if (!response.ok) {
    throw new ApiError('CM media upload failed', response.status, body);
  }
  try {
    return parseCmMediaUploadBody(body);
  } catch (err) {
    throw new ApiError('CM media upload response was invalid', response.status, {
      parse_error: err instanceof Error ? err.message : 'invalid_response',
      body,
    });
  }
}
