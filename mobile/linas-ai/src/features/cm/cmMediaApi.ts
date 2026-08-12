/** Upload CM article media (case examples) for knowledge/care drafts. */

import { z } from 'zod';

import { ApiError, apiUpload } from '../../api/client';
import { appendLocalFile } from '../../api/formDataFile';

const UploadSchema = z
  .object({
    success: z.literal(true),
    media_id: z.string(),
    filename: z.string().optional(),
    mime: z.string().optional(),
    kind: z.enum(['image', 'file']).optional(),
    size: z.number().optional(),
  })
  .passthrough();

export type CmMediaUploadResult = z.infer<typeof UploadSchema>;

export async function uploadCmArticleMedia(file: {
  uri: string;
  name: string;
  mimeType: string;
}): Promise<CmMediaUploadResult> {
  const response = await apiUpload('/api/cm/media', () => {
    const form = new FormData();
    // Expo 57 global fetch rejects RN `{uri,name,type}` FormData parts.
    appendLocalFile(form, 'file', file.uri, { name: file.name });
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
  return UploadSchema.parse(body);
}
