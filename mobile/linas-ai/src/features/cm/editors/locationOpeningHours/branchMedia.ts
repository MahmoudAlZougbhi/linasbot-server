import { asRecordList, newId } from '../../cmApi';

export type BranchAttachment = {
  id: string;
  kind: 'image' | 'video' | 'file' | 'link';
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
      caption: String(row.caption || ''),
      mime: String(row.mime || ''),
      filename: String(row.filename || ''),
      size: typeof row.size === 'number' ? row.size : 0,
      url: String(row.url || ''),
    };
  });
}

export function newLinkAttachment(url: string, title: string): BranchAttachment {
  const href = url.trim();
  const name = title.trim() || href;
  return {
    id: newId('link'),
    kind: 'link',
    caption: '',
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
