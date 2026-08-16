/** Pure Knowledge list/edit helpers (no React Native). */

export const LOCATIONS_KNOWLEDGE_TITLE = 'Opening hours & locations';

export type KnowledgeKind = 'image' | 'file' | 'video' | 'link';

export type KnowledgeAttachment = {
  id: string;
  kind: KnowledgeKind;
  title: string;
  description: string;
  caption: string;
  mime: string;
  filename: string;
  size: number;
  url: string;
  duration_seconds: number | null;
};

export type KnowledgeItem = {
  id: string;
  title: string;
  body: string;
  tags: string[];
  language: string;
  audience: string;
  category: string;
  status: string;
  source_filename: string | null;
  source_checksum: string | null;
  linked_service_ids: string[];
  linked_branch_ids: string[];
  notes: string | null;
  attachments: KnowledgeAttachment[];
  updated_at: string | null;
};

export type KnowledgeListRow =
  | { type: 'article'; item: KnowledgeItem }
  | { type: 'locations' };

export type MediaCounts = {
  images: number;
  videos: number;
  pdfs: number;
  files: number;
  links: number;
};

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

function asStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map(String);
}

export function isLocationsKnowledgeTitle(title: string): boolean {
  const t = title.trim().toLowerCase();
  return t === 'opening hours & locations' || t === 'opening hours and locations';
}

export function countWords(text: string): number {
  const trimmed = text.trim();
  if (!trimmed) return 0;
  return trimmed.split(/\s+/).filter(Boolean).length;
}

export function isPdfAttachment(att: KnowledgeAttachment): boolean {
  const mime = att.mime.toLowerCase();
  const name = att.filename.toLowerCase();
  return mime === 'application/pdf' || mime.includes('pdf') || name.endsWith('.pdf');
}

export function normalizeAttachmentKind(row: KnowledgeAttachment): KnowledgeAttachment {
  const mime = row.mime.toLowerCase();
  if (row.kind === 'link' || row.url.trim()) {
    return { ...row, kind: 'link' };
  }
  if (row.kind === 'video' || mime.startsWith('video/')) {
    return { ...row, kind: 'video' };
  }
  if (row.kind === 'image' || mime.startsWith('image/')) {
    return { ...row, kind: 'image' };
  }
  return { ...row, kind: 'file' };
}

function parseResourceFields(row: Record<string, unknown>): { title: string; description: string } {
  return {
    title: String(row.title || '').trim(),
    description: String(row.description || row.caption || '').trim(),
  };
}

function serializeResourceFields(fields: { title: string; description: string }): {
  title: string;
  description: string;
  caption: string;
} {
  const title = fields.title.trim();
  const description = fields.description.trim();
  return { title, description, caption: description };
}

export function parseAttachment(row: Record<string, unknown>): KnowledgeAttachment {
  const durationRaw = row.duration_seconds;
  const duration =
    typeof durationRaw === 'number' && Number.isFinite(durationRaw) && durationRaw >= 0
      ? Math.round(durationRaw)
      : null;
  const meta = parseResourceFields(row);
  return normalizeAttachmentKind({
    id: String(row.id || ''),
    kind: row.kind === 'image' || row.kind === 'video' || row.kind === 'link' ? row.kind : 'file',
    title: meta.title,
    description: meta.description,
    caption: meta.description,
    mime: String(row.mime || ''),
    filename: String(row.filename || ''),
    size: typeof row.size === 'number' && Number.isFinite(row.size) ? row.size : 0,
    url: String(row.url || ''),
    duration_seconds: duration,
  });
}

export function parseKnowledgeItem(row: Record<string, unknown>): KnowledgeItem {
  const atts = Array.isArray(row.attachments) ? row.attachments : [];
  return {
    id: String(row.id || ''),
    title: String(row.title || ''),
    body: String(row.body || ''),
    tags: asStringList(row.tags),
    language: String(row.language || ''),
    audience: String(row.audience || 'general'),
    category: String(row.category || ''),
    status: String(row.status || 'active'),
    source_filename: row.source_filename == null ? null : String(row.source_filename),
    source_checksum: row.source_checksum == null ? null : String(row.source_checksum),
    linked_service_ids: asStringList(row.linked_service_ids),
    linked_branch_ids: asStringList(row.linked_branch_ids),
    notes: row.notes == null ? null : String(row.notes),
    attachments: atts
      .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object')
      .map(parseAttachment),
    updated_at: row.updated_at == null || row.updated_at === '' ? null : String(row.updated_at),
  };
}

export function itemToRecord(item: KnowledgeItem): Record<string, unknown> {
  return {
    id: item.id,
    title: item.title,
    body: item.body,
    tags: item.tags,
    language: item.language,
    audience: item.audience,
    category: item.category,
    status: item.status,
    source_filename: item.source_filename,
    source_checksum: item.source_checksum,
    linked_service_ids: item.linked_service_ids,
    linked_branch_ids: item.linked_branch_ids,
    notes: item.notes,
    attachments: item.attachments.map((att) => {
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
      };
    }),
    updated_at: item.updated_at,
  };
}

export function createKnowledgeItem(id: string, nowIso: string): KnowledgeItem {
  return {
    id,
    title: '',
    body: '',
    tags: [],
    language: '',
    audience: 'general',
    category: '',
    status: 'active',
    source_filename: null,
    source_checksum: null,
    linked_service_ids: [],
    linked_branch_ids: [],
    notes: null,
    attachments: [],
    updated_at: nowIso,
  };
}

export function touchUpdated(item: KnowledgeItem, nowIso: string): KnowledgeItem {
  return { ...item, updated_at: nowIso };
}

export function countMedia(attachments: KnowledgeAttachment[]): MediaCounts {
  const counts: MediaCounts = { images: 0, videos: 0, pdfs: 0, files: 0, links: 0 };
  for (const raw of attachments) {
    const att = normalizeAttachmentKind(raw);
    if (att.kind === 'link') counts.links += 1;
    else if (att.kind === 'image') counts.images += 1;
    else if (att.kind === 'video') counts.videos += 1;
    else if (isPdfAttachment(att)) counts.pdfs += 1;
    else counts.files += 1;
  }
  return counts;
}

function part(count: number, one: string, many: string): string | null {
  if (count <= 0) return null;
  return `${count} ${count === 1 ? one : many}`;
}

export function formatMediaSummary(counts: MediaCounts): string {
  const bits = [
    part(counts.images, 'image', 'images'),
    part(counts.videos, 'video', 'videos'),
    part(counts.pdfs, 'PDF', 'PDFs'),
    part(counts.files, 'file', 'files'),
    part(counts.links, 'link', 'links'),
  ].filter((bit): bit is string => Boolean(bit));
  return bits.length ? bits.join(' • ') : 'Text only';
}

export function formatDuration(seconds: number): string {
  const total = Math.max(0, Math.round(seconds));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

export function formatBytes(size: number): string {
  if (size < 1024) return `${Math.max(0, Math.round(size))} B`;
  if (size < 1024 * 1024) {
    const kb = size / 1024;
    return kb >= 10 ? `${Math.round(kb)} KB` : `${kb.toFixed(1)} KB`;
  }
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

export function isSameLocalDay(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

/** Returns '' | 'today' | 'Aug 14' (caller prefixes "Updated "). */
export function formatUpdatedStamp(iso: string | null, now = new Date()): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  if (isSameLocalDay(d, now)) return 'today';
  return `${MONTHS[d.getMonth()]} ${d.getDate()}`;
}

export function matchesQuery(item: KnowledgeItem, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  const blob = `${item.title} ${item.body} ${item.source_filename || ''}`.toLowerCase();
  return blob.includes(q);
}

export function locationsRowMatches(query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return LOCATIONS_KNOWLEDGE_TITLE.toLowerCase().includes(q) || 'opening hours'.includes(q);
}

export function buildKnowledgeList(items: KnowledgeItem[], query: string): KnowledgeListRow[] {
  const articles = items
    .filter((item) => !isLocationsKnowledgeTitle(item.title))
    .filter((item) => item.status !== 'archived')
    .filter((item) => matchesQuery(item, query))
    .map((item) => ({ type: 'article' as const, item }));
  const rows: KnowledgeListRow[] = [...articles];
  if (locationsRowMatches(query)) {
    rows.push({ type: 'locations' });
  }
  return rows;
}

export function isPublishedStatus(status: string): boolean {
  return status === 'active';
}

export function togglePublishedStatus(status: string): string {
  return status === 'active' ? 'draft' : 'active';
}

export function isValidHttpUrl(value: string): boolean {
  const trimmed = value.trim();
  try {
    const parsed = new URL(trimmed);
    return parsed.protocol === 'http:' || parsed.protocol === 'https:';
  } catch {
    return false;
  }
}
