/** Pure request-rule helpers (CM requests_appointments + request graphs). */

export type RequestRuleType = 'APPOINTMENT' | 'ORDER' | 'OTHER';

export type RequestRuleItem = {
  id: string;
  type: RequestRuleType;
  name: string;
  notes: string;
  enabled: boolean;
};

export type RequestField = { key: string; label: string };

export type RequestGraphRow = {
  definition_id: string;
  source_item_id: string;
  status: string;
  title: string;
  destination: string;
  required_information: RequestField[];
};

const TYPES: RequestRuleType[] = ['APPOINTMENT', 'ORDER', 'OTHER'];

function asFields(value: unknown): RequestField[] {
  if (!Array.isArray(value)) return [];
  const out: RequestField[] = [];
  for (const raw of value) {
    if (!raw || typeof raw !== 'object') continue;
    const rec = raw as Record<string, unknown>;
    const key = String(rec.key || rec.label || '').trim();
    const label = String(rec.label || rec.key || '').trim();
    if (!key && !label) continue;
    out.push({ key: key || label, label: label || key });
  }
  return out;
}

export function parseRequestRule(row: Record<string, unknown>): RequestRuleItem {
  const raw = String(row.type || '').toUpperCase();
  const type = TYPES.includes(raw as RequestRuleType) ? (raw as RequestRuleType) : 'APPOINTMENT';
  return {
    id: String(row.id || ''),
    type,
    name: String(row.name || row.title || ''),
    notes: row.notes == null ? '' : String(row.notes),
    enabled: row.enabled !== false,
  };
}

export function ruleToRecord(item: RequestRuleItem): Record<string, unknown> {
  return {
    id: item.id,
    type: item.type,
    name: item.name,
    notes: item.notes.trim() || null,
    enabled: item.enabled,
  };
}

export function createRequestRule(id: string): RequestRuleItem {
  return { id, type: 'APPOINTMENT', name: '', notes: '', enabled: true };
}

export function matchesRequestQuery(item: RequestRuleItem, query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (!needle) return true;
  return `${item.name} ${item.notes} ${item.type}`.toLowerCase().includes(needle);
}

export function destinationFromType(type: RequestRuleType): string {
  if (type === 'APPOINTMENT') return 'appointment';
  if (type === 'ORDER') return 'order';
  return 'general';
}

export function parseGraphRow(row: Record<string, unknown>): RequestGraphRow {
  return {
    definition_id: String(row.definition_id || ''),
    source_item_id: String(row.source_item_id || ''),
    status: String(row.status || ''),
    title: String(row.title || ''),
    destination: String(row.destination || ''),
    required_information: asFields(row.required_information),
  };
}

export function isGraphPublished(graph: RequestGraphRow | undefined): boolean {
  return String(graph?.status || '').toLowerCase() === 'active';
}

export function collectsPhrase(graph: RequestGraphRow | undefined, empty: string): string {
  const labels = (graph?.required_information || []).map((row) => row.label).filter(Boolean);
  if (!labels.length) return empty;
  if (labels.length === 1) return labels[0];
  if (labels.length === 2) return `${labels[0]} and ${labels[1]}`;
  return `${labels.slice(0, -1).join(', ')} and ${labels[labels.length - 1]}`;
}

export function typeLabelKey(
  type: RequestRuleType,
): 'aiSetupRequestTypeAppointment' | 'aiSetupRequestTypeOrder' | 'aiSetupRequestTypeOther' {
  if (type === 'ORDER') return 'aiSetupRequestTypeOrder';
  if (type === 'OTHER') return 'aiSetupRequestTypeOther';
  return 'aiSetupRequestTypeAppointment';
}
