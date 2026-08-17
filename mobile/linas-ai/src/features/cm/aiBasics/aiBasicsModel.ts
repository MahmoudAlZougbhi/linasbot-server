/** Pure AI Basics / greeting helpers (no React Native, no cross-folder imports). */

export type GreetingKind = 'image' | 'file' | 'video' | 'link';

export type GreetingAttachment = {
  id: string;
  kind: GreetingKind;
  title: string;
  description: string;
  caption: string;
  mime: string;
  filename: string;
  size: number;
  url: string;
  duration_seconds: number | null;
};

export type GreetingRule = {
  id: string;
  enabled: boolean;
  name: string;
  notes: string;
  en: string;
  ar: string;
  fr: string;
  trigger_mode: string;
  trigger_pattern: string;
  keywords: string[];
  attachments: GreetingAttachment[];
};

function str(value: unknown): string {
  return value == null ? '' : String(value);
}

function asRecordList(value: unknown): Record<string, unknown>[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is Record<string, unknown> => !!item && typeof item === 'object');
}

function newId(prefix: string): string {
  return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

function parseAttachment(row: Record<string, unknown>): GreetingAttachment {
  const durationRaw = row.duration_seconds;
  const duration =
    typeof durationRaw === 'number' && Number.isFinite(durationRaw) && durationRaw >= 0
      ? Math.round(durationRaw)
      : null;
  const description = str(row.description || row.caption).trim();
  const title = str(row.title).trim();
  let kind: GreetingKind =
    row.kind === 'image' || row.kind === 'video' || row.kind === 'link' ? row.kind : 'file';
  const mime = str(row.mime).toLowerCase();
  const url = str(row.url);
  if (kind === 'link' || url.trim()) kind = 'link';
  else if (mime.startsWith('video/')) kind = 'video';
  else if (mime.startsWith('image/')) kind = 'image';
  return {
    id: str(row.id),
    kind,
    title,
    description,
    caption: description,
    mime: str(row.mime),
    filename: str(row.filename),
    size: typeof row.size === 'number' && Number.isFinite(row.size) ? row.size : 0,
    url,
    duration_seconds: duration,
  };
}

export function greetingNote(item: GreetingRule | Record<string, unknown>): string {
  const notes = str('notes' in item ? item.notes : '');
  if (notes) return notes;
  return str('en' in item ? item.en : '');
}

/** Keep trailing spaces while typing — do not trim. */
export function withGreetingNote(item: GreetingRule, note: string): GreetingRule {
  return {
    ...item,
    notes: note,
    en: note,
    trigger_mode: item.trigger_mode || 'always',
    enabled: item.enabled !== false,
  };
}

export function parseGreeting(row: Record<string, unknown>): GreetingRule {
  const atts = Array.isArray(row.attachments) ? row.attachments : [];
  const notes = greetingNote(row);
  return {
    id: str(row.id),
    enabled: row.enabled !== false,
    name: str(row.name),
    notes,
    en: str(row.en) || notes,
    ar: str(row.ar),
    fr: str(row.fr),
    trigger_mode: str(row.trigger_mode) || 'always',
    trigger_pattern: str(row.trigger_pattern),
    keywords: Array.isArray(row.keywords) ? row.keywords.map((k) => str(k)).filter(Boolean) : [],
    attachments: atts
      .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object')
      .map(parseAttachment),
  };
}

export function greetingToRecord(item: GreetingRule): Record<string, unknown> {
  return {
    id: item.id,
    enabled: item.enabled !== false,
    name: item.name,
    trigger_mode: item.trigger_mode || 'always',
    trigger_pattern: item.trigger_pattern,
    keywords: item.keywords,
    ar: item.ar,
    en: item.en || item.notes,
    fr: item.fr,
    notes: item.notes || null,
    attachments: item.attachments.map((att) => {
      const title = att.title.trim();
      const description = (att.description || att.caption).trim();
      return {
        id: att.id,
        kind: att.kind,
        title,
        description,
        caption: description,
        mime: att.mime,
        filename: att.filename,
        size: att.size,
        url: att.url,
        duration_seconds: att.duration_seconds,
        status: 'active',
      };
    }),
  };
}

export function parseGreetings(payload: Record<string, unknown>): GreetingRule[] {
  return asRecordList(payload.items).map(parseGreeting);
}

export function emptyGreeting(): GreetingRule {
  return {
    id: newId('greet'),
    enabled: true,
    name: '',
    notes: '',
    en: '',
    ar: '',
    fr: '',
    trigger_mode: 'always',
    trigger_pattern: '',
    keywords: [],
    attachments: [],
  };
}

export function matchesGreetingQuery(item: GreetingRule, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return `${item.name} ${item.notes}`.toLowerCase().includes(q);
}

export const STYLE_TONE = ['Warm', 'Friendly', 'Direct'] as const;
export const STYLE_FORMALITY = ['Casual', 'Balanced', 'Formal'] as const;
export const STYLE_EMOJI = ['None', 'Light', 'Expressive'] as const;
