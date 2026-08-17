import { normalizeWeeklySchedule } from './branchScheduleHelpers';

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function asRecordList(value: unknown): Record<string, unknown>[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is Record<string, unknown> => !!item && typeof item === 'object');
}

function normalizeAttachment(row: Record<string, unknown>): Record<string, unknown> {
  const kindRaw = String(row.kind || 'file');
  const kind =
    kindRaw === 'image' || kindRaw === 'video' || kindRaw === 'link' ? kindRaw : 'file';
  const description = String(row.description || row.caption || '').trim();
  return {
    id: String(row.id || ''),
    kind,
    title: String(row.title || '').trim(),
    description,
    caption: description,
    mime: String(row.mime || ''),
    filename: String(row.filename || ''),
    size: typeof row.size === 'number' ? row.size : 0,
    url: String(row.url || ''),
  };
}

/** Align a branch row with what the editor reads/writes so open-and-back stays clean. */
export function normalizeBranchDraftItem(raw: Record<string, unknown>): Record<string, unknown> {
  const labels = asRecord(raw.labels);
  return {
    ...raw,
    labels: {
      en: String(labels.en || ''),
      ar: String(labels.ar || ''),
      fr: String(labels.fr || ''),
      franco: String(labels.franco || ''),
    },
    address: String(raw.address || ''),
    street: String(raw.street || ''),
    building: String(raw.building || ''),
    floor: String(raw.floor || ''),
    country: String(raw.country || ''),
    maps_url: String(raw.maps_url || ''),
    weekly_schedule: normalizeWeeklySchedule(raw.weekly_schedule),
    notes: raw.notes == null || raw.notes === '' ? null : String(raw.notes),
    attachments: asRecordList(raw.attachments).map(normalizeAttachment),
    available: raw.available !== false,
  };
}

/** Normalize Locations draft before baseline snapshot. */
export function normalizeBranchesDraftPayload(payload: Record<string, unknown>): Record<string, unknown> {
  return {
    ...payload,
    items: asRecordList(payload.items).map(normalizeBranchDraftItem),
    timezone: String(payload.timezone || '').trim() || 'Asia/Beirut',
    specific_off_rules: Array.isArray(payload.specific_off_rules) ? payload.specific_off_rules : [],
    policy_text: payload.policy_text == null ? '' : String(payload.policy_text),
    notes: payload.notes == null || payload.notes === '' ? null : String(payload.notes),
  };
}
