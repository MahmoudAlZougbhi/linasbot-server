import { asRecordList, newId } from '../cmApi';
import {
  parseAttachment,
  type KnowledgeAttachment,
} from '../knowledge/knowledgeModel';
import { serializeResourceFields } from '../resources/resourceMeta';

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
  attachments: KnowledgeAttachment[];
};

function str(value: unknown): string {
  return value == null ? '' : String(value);
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
      const meta = serializeResourceFields({
        title: att.title,
        description: att.description || att.caption,
      });
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
