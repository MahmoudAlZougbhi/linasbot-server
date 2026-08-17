/** Shared AI Setup resource title/description helpers (no React Native). */

export type ResourceKind = 'image' | 'video' | 'file' | 'link';

export type ResourceMetaFields = {
  title: string;
  description: string;
};

export type ResourceMetaError = 'title' | 'description' | 'url';

export function parseResourceFields(row: Record<string, unknown>): ResourceMetaFields {
  const description = String(row.description || row.caption || '').trim();
  return {
    title: String(row.title || '').trim(),
    description,
  };
}

export function suggestedTitleFromFilename(filename: string): string {
  const base = filename.replace(/\.[^.]+$/, '').trim();
  if (!base) return '';
  const hex = base.replace(/[-_\s]/g, '');
  if (/^[0-9a-f]{32,}$/i.test(hex)) return '';
  return base.replace(/[_-]+/g, ' ').trim();
}

export function resourceMetaError(
  kind: ResourceKind,
  fields: ResourceMetaFields,
  url = '',
): ResourceMetaError | null {
  if (!fields.title.trim()) return 'title';
  if (!fields.description.trim()) return 'description';
  if (kind === 'link' && !String(url || '').trim()) return 'url';
  return null;
}

export function serializeResourceFields(fields: ResourceMetaFields): ResourceMetaFields & { caption: string } {
  const title = fields.title.trim();
  const description = fields.description.trim();
  return { title, description, caption: description };
}

export function moveById<T extends { id: string }>(rows: T[], id: string, direction: -1 | 1): T[] {
  const index = rows.findIndex((row) => row.id === id);
  const next = index + direction;
  if (index < 0 || next < 0 || next >= rows.length) return rows;
  const copy = rows.slice();
  const [item] = copy.splice(index, 1);
  copy.splice(next, 0, item);
  return copy;
}
