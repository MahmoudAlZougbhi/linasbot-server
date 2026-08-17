/** Types and display helpers for AI Setup Services. */

export type ServiceKind = 'image' | 'file' | 'video' | 'link';

export type ServiceAttachment = {
  id: string;
  kind: ServiceKind;
  title: string;
  description: string;
  caption: string;
  mime: string;
  filename: string;
  size: number;
  url: string;
  duration_seconds: number | null;
};

export type ServiceDetail = { key: string; value: string };

export type ServicePrice = {
  id: string;
  title: string;
  amount: number;
  currency: string;
  durationMinutes: number | null;
  details: ServiceDetail[];
  subtitle: string;
};

export type ServiceItem = {
  id: string;
  name: string;
  note: string;
  attachments: ServiceAttachment[];
  prices: ServicePrice[];
  raw: Record<string, unknown>;
};

export type PriceDraft = {
  id: string | null;
  title: string;
  amountText: string;
  details: ServiceDetail[];
};

export function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

export function asRecordList(value: unknown): Record<string, unknown>[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object');
}

export function emptyLabels(): Record<string, string> {
  return { en: '', ar: '', fr: '', franco: '' };
}

export function primaryLabel(labels: unknown): string {
  const rec = asRecord(labels);
  for (const key of ['en', 'ar', 'fr', 'franco']) {
    const v = rec[key];
    if (typeof v === 'string' && v.trim()) return v;
  }
  return '';
}

export function slugDimension(key: string): string {
  return key
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_|_$/g, '');
}

export function isDurationKey(key: string): boolean {
  const k = key.trim().toLowerCase().replace(/\s+/g, '_');
  return k === 'duration' || k === 'time' || k === 'duration_minutes';
}

export function parseDurationMinutes(value: string): number | null {
  const t = value.trim().toLowerCase();
  if (!t) return null;
  const hm = t.match(/^(\d+)\s*h(?:ours?)?\s*(\d+)\s*m/);
  if (hm) return Number(hm[1]) * 60 + Number(hm[2]);
  const hour = t.match(/^(\d+(?:\.\d+)?)\s*h(?:ours?)?$/);
  if (hour) return Math.round(Number(hour[1]) * 60);
  const min = t.match(/^(\d+)\s*m(?:in(?:utes?)?)?$/);
  if (min) return Number(min[1]);
  if (/^\d+$/.test(t)) return Number(t);
  return null;
}

export function formatDuration(minutes: number | null): string {
  if (minutes == null || minutes <= 0 || !Number.isFinite(minutes)) return '';
  const total = Math.round(minutes);
  const h = Math.floor(total / 60);
  const m = total % 60;
  if (h > 0 && m === 0) return h === 1 ? '1 hour' : `${h} hours`;
  if (h > 0) return `${h} hour${h === 1 ? '' : 's'} ${m} min`;
  return `${m} min`;
}

export function formatMoney(amount: number, currency = 'USD'): string {
  if (!Number.isFinite(amount) || amount <= 0) return 'Free';
  const whole = Number.isInteger(amount) ? String(amount) : amount.toFixed(2).replace(/\.?0+$/, '');
  if (currency === 'USD' || !currency) return `$${whole}`;
  return `${whole} ${currency}`;
}

export function parseAmount(text: string): number | null {
  const cleaned = text.replace(/[^0-9.]/g, '');
  if (!cleaned) return null;
  const n = Number(cleaned);
  if (!Number.isFinite(n) || n < 0) return null;
  return n;
}

export function emptyDetails(): ServiceDetail[] {
  return [
    { key: '', value: '' },
    { key: '', value: '' },
  ];
}

export function emptyPriceDraft(): PriceDraft {
  return { id: null, title: '', amountText: '', details: emptyDetails() };
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

export function lowestAmount(prices: ServicePrice[]): number | null {
  if (!prices.length) return null;
  return prices.reduce((min, row) => Math.min(min, row.amount), prices[0].amount);
}

export function formatPriceFooter(prices: ServicePrice[]): string {
  const count = prices.length;
  if (count === 0) return '0 price options';
  const optionLabel = count === 1 ? '1 price option' : `${count} price options`;
  const low = lowestAmount(prices);
  if (low == null) return optionLabel;
  if (low <= 0) return `${optionLabel} · Free`;
  return `${optionLabel} · From ${formatMoney(low, prices[0]?.currency || 'USD')}`;
}

export function formatMediaCount(count: number): string {
  return `${count} media & files`;
}
