import { parseAttachment, type KnowledgeAttachment } from '../cm/knowledge/knowledgeModel';
import { serializeResourceFields } from '../cm/resources/resourceMeta';
import type { FaqGroup } from './faqApi';

export function parseFaqAttachments(group: FaqGroup): KnowledgeAttachment[] {
  const raw = (group as { attachments?: unknown }).attachments;
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((row): row is Record<string, unknown> => Boolean(row) && typeof row === 'object')
    .map(parseAttachment)
    .filter((row) => row.id);
}

export function serializeFaqAttachments(rows: KnowledgeAttachment[]): Record<string, unknown>[] {
  return rows.map((att, index) => {
    const meta = serializeResourceFields({ title: att.title, description: att.description || att.caption });
    return {
      id: att.id,
      kind: att.kind,
      title: meta.title,
      description: meta.description,
      caption: meta.caption,
      mime: att.mime,
      filename: att.filename,
      size: att.size,
      url: att.url,
      duration_seconds: att.duration_seconds,
      status: 'active',
      sort_order: index,
    };
  });
}
