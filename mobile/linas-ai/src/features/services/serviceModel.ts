/** Parse/serialize CM prices catalog items as Services. */

import {
  asRecord,
  asRecordList,
  emptyDetails,
  emptyLabels,
  formatDuration,
  isDurationKey,
  parseDurationMinutes,
  primaryLabel,
  slugDimension,
  type PriceDraft,
  type ServiceAttachment,
  type ServiceDetail,
  type ServiceItem,
  type ServicePrice,
} from './serviceFormat';

export * from './serviceFormat';

export function normalizeAttachmentKind(row: ServiceAttachment): ServiceAttachment {
  const mime = row.mime.toLowerCase();
  if (row.kind === 'link' || row.url.trim()) return { ...row, kind: 'link' };
  if (row.kind === 'video' || mime.startsWith('video/')) return { ...row, kind: 'video' };
  if (row.kind === 'image' || mime.startsWith('image/')) return { ...row, kind: 'image' };
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

export function parseAttachment(row: Record<string, unknown>): ServiceAttachment {
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

function attachmentToRecord(att: ServiceAttachment): Record<string, unknown> {
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
}

function serviceNoteFromCatalog(row: Record<string, unknown>): string {
  const desc = String(row.description || '');
  if (desc.trim()) return desc;
  const notes = String(row.notes || '');
  if (!notes.trim()) return '';
  if (/^book[_-]/i.test(notes.trim())) return '';
  return notes;
}

function detailsFromDimensions(dims: Record<string, unknown>): ServiceDetail[] {
  const rows = Object.entries(dims)
    .map(([key, value]) => ({ key: key.replace(/_/g, ' '), value: String(value || '') }))
    .filter((row) => row.key.trim() || row.value.trim());
  return rows.length ? rows : emptyDetails();
}

function composeTitle(notes: string, details: ServiceDetail[]): string {
  if (notes.trim()) return notes.trim();
  return details
    .map((row) => row.value.trim())
    .filter(Boolean)
    .join(' · ');
}

function composeSubtitle(durationMinutes: number | null, details: ServiceDetail[]): string {
  const dur = formatDuration(durationMinutes);
  if (dur) return dur;
  const durationDetail = details.find((row) => isDurationKey(row.key) && row.value.trim());
  if (durationDetail) return durationDetail.value.trim();
  return details.find((row) => row.value.trim() && !isDurationKey(row.key))?.value.trim() || '';
}

export function parsePriceEntry(row: Record<string, unknown>): ServicePrice {
  const details = detailsFromDimensions(asRecord(row.dimensions));
  const durationRaw = row.duration_minutes;
  const durationMinutes =
    typeof durationRaw === 'number' && Number.isFinite(durationRaw) && durationRaw > 0
      ? Math.round(durationRaw)
      : null;
  const amount = typeof row.amount === 'number' && Number.isFinite(row.amount) ? row.amount : Number(row.amount) || 0;
  return {
    id: String(row.id || ''),
    title: composeTitle(String(row.notes || ''), details),
    amount,
    currency: String(row.currency || 'USD'),
    durationMinutes,
    details,
    subtitle: composeSubtitle(durationMinutes, details),
  };
}

export function parseServiceItem(
  row: Record<string, unknown>,
  entries: Record<string, unknown>[],
): ServiceItem {
  const id = String(row.id || '');
  const prices = entries.filter((entry) => String(entry.catalog_item_id || '') === id).map(parsePriceEntry);
  const atts = Array.isArray(row.attachments) ? row.attachments : [];
  return {
    id,
    name: primaryLabel(row.labels) || String(row.id || ''),
    note: serviceNoteFromCatalog(row),
    attachments: atts
      .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object')
      .map(parseAttachment),
    prices,
    raw: row,
  };
}

export function parseServices(payload: Record<string, unknown>): ServiceItem[] {
  const catalog = asRecordList(payload.catalog);
  const entries = asRecordList(payload.price_entries);
  return catalog.map((row) => parseServiceItem(row, entries));
}

export function matchesServiceQuery(item: ServiceItem, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  const prices = item.prices.map((row) => `${row.title} ${row.subtitle}`).join(' ');
  const blob = `${item.name} ${item.note} ${prices}`.toLowerCase();
  return blob.includes(q);
}

export function createCatalogItem(id: string): Record<string, unknown> {
  return {
    id,
    item_type: 'service',
    category_ids: [],
    labels: emptyLabels(),
    aliases: [],
    description: '',
    base_price: null,
    currency: 'USD',
    variants: [],
    branch_ids: [],
    audience: 'any',
    unit: null,
    discount_eligible: true,
    active: true,
    effective: {},
    provenance: 'mobile_services_ui',
    revision: 1,
    notes: null,
    attachments: [],
  };
}

export function patchCatalogItem(
  raw: Record<string, unknown>,
  patch: { name?: string; note?: string; attachments?: ServiceAttachment[] },
): Record<string, unknown> {
  const labels = { ...emptyLabels(), ...asRecord(raw.labels) };
  if (patch.name != null) labels.en = patch.name;
  return {
    ...raw,
    labels,
    description: patch.note != null ? patch.note : raw.description,
    attachments: patch.attachments != null ? patch.attachments.map(attachmentToRecord) : raw.attachments,
    item_type: raw.item_type || 'service',
    active: raw.active !== false,
  };
}

export function detailsToDimensions(details: ServiceDetail[]): Record<string, string> {
  const dims: Record<string, string> = {};
  for (const row of details) {
    const id = slugDimension(row.key || row.value);
    if (!id || !row.value.trim()) continue;
    dims[id] = row.value.trim();
  }
  return dims;
}

export function durationFromDetails(details: ServiceDetail[]): number | null {
  for (const row of details) {
    if (!isDurationKey(row.key)) continue;
    const parsed = parseDurationMinutes(row.value);
    if (parsed != null) return parsed;
  }
  return null;
}

export function ensureDimensionDefs(
  defs: Record<string, unknown>[],
  details: ServiceDetail[],
): Record<string, unknown>[] {
  let next = defs;
  for (const row of details) {
    const id = slugDimension(row.key);
    if (!id) continue;
    const existing = next.find((d) => String(d.id) === id);
    const value = row.value.trim();
    if (!existing) {
      next = [
        ...next,
        {
          id,
          labels: { ...emptyLabels(), en: row.key.trim() },
          value_type: 'string',
          allowed_values: value ? [value] : [],
          required: false,
          active: true,
          notes: null,
        },
      ];
      continue;
    }
    const allowed = Array.isArray(existing.allowed_values) ? existing.allowed_values.map(String) : [];
    const nextAllowed = value && !allowed.includes(value) ? [...allowed, value] : allowed;
    next = next.map((d) => (String(d.id) === id ? { ...d, allowed_values: nextAllowed, active: true } : d));
  }
  return next;
}

export function priceDraftFromEntry(price: ServicePrice): PriceDraft {
  return {
    id: price.id,
    title: price.title,
    amountText: price.amount > 0 ? String(price.amount) : '',
    details: price.details.length ? price.details.map((row) => ({ ...row })) : emptyDetails(),
  };
}

export function buildPriceEntry(
  id: string,
  catalogItemId: string,
  draft: PriceDraft,
  amount: number,
): Record<string, unknown> {
  const details = draft.details.filter((row) => row.key.trim() || row.value.trim());
  return {
    id,
    catalog_item_id: catalogItemId,
    variant_id: null,
    amount,
    currency: 'USD',
    branch_id: null,
    audience: 'any',
    unit: null,
    min_quantity: null,
    max_quantity: null,
    duration_minutes: durationFromDetails(details),
    size: null,
    dimensions: detailsToDimensions(details),
    active: true,
    effective: {},
    provenance: 'mobile_services_ui',
    revision: 1,
    notes: draft.title.trim() || null,
  };
}
