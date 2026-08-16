import { asRecordList, newId } from '../../cmApi';

export type BranchAttachment = {
  id: string;
  kind: 'image' | 'video' | 'file' | 'link';
  title: string;
  description: string;
  caption: string;
  mime: string;
  filename: string;
  size: number;
  url: string;
};

export function asBranchAttachments(value: unknown): BranchAttachment[] {
  return asRecordList(value).map((row) => {
    const kindRaw = String(row.kind || 'file');
    const kind: BranchAttachment['kind'] =
      kindRaw === 'image' || kindRaw === 'video' || kindRaw === 'link' ? kindRaw : 'file';
    return {
      id: String(row.id || ''),
      kind,
      title: String(row.title || '').trim(),
      description: String(row.description || row.caption || '').trim(),
      caption: String(row.description || row.caption || '').trim(),
      mime: String(row.mime || ''),
      filename: String(row.filename || ''),
      size: typeof row.size === 'number' ? row.size : 0,
      url: String(row.url || ''),
    };
  });
}

export function newLinkAttachment(url: string, title: string, description = ''): BranchAttachment {
  const href = url.trim();
  const name = title.trim() || href;
  const desc = description.trim();
  return {
    id: newId('link'),
    kind: 'link',
    title: name,
    description: desc,
    caption: desc,
    mime: '',
    filename: name,
    size: 0,
    url: href,
  };
}

export function hrefForOpen(url: string): string {
  const raw = url.trim();
  if (!raw) return '';
  if (/^[a-z][a-z0-9+.-]*:/i.test(raw)) return raw;
  return `https://${raw}`;
}
