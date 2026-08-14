import type { ChatChannel } from '../livechat/liveChatTypes';
import type { RequestCard, RequestDetail, StatusBucket } from './requestsTypes';

const IN_PROGRESS = ['IN_REVIEW', 'WAITING_FOR_CUSTOMER', 'CONFIRMED', 'READY'] as const;

export const FILTER_PLATFORMS: { id: string; channel: ChatChannel | 'all' }[] = [
  { id: 'all', channel: 'all' },
  { id: 'whatsapp_cloud', channel: 'whatsapp' },
  { id: 'instagram_dm', channel: 'instagram' },
  { id: 'facebook_messenger', channel: 'facebook' },
  { id: 'tiktok', channel: 'tiktok' },
];

export function requestChannel(source: string | null | undefined): ChatChannel {
  const ch = String(source || '').toLowerCase();
  if (ch.includes('tiktok')) return 'tiktok';
  if (ch.includes('instagram')) return 'instagram';
  if (ch.includes('facebook') || ch.includes('messenger')) return 'facebook';
  return 'whatsapp';
}

export function statusBucket(status: string): StatusBucket | 'cancelled' {
  if (status === 'NEW') return 'new';
  if (status === 'COMPLETED') return 'done';
  if (status === 'CANCELLED') return 'cancelled';
  return 'in_progress';
}

export function bucketStatuses(bucket: StatusBucket): string[] {
  if (bucket === 'new') return ['NEW'];
  if (bucket === 'done') return ['COMPLETED'];
  return [...IN_PROGRESS];
}

export function bucketCounts(counts: Record<string, number>): Record<StatusBucket, number> {
  return {
    new: counts.NEW ?? 0,
    in_progress: IN_PROGRESS.reduce((sum, key) => sum + (counts[key] ?? 0), 0),
    done: counts.COMPLETED ?? 0,
  };
}

/** Single valid transition toward the inbox bucket, or null if already there / not allowed. */
export function nextStatusForBucket(item: RequestCard, bucket: StatusBucket): string | null {
  const current = statusBucket(item.status);
  if (current === bucket) return null;
  if (bucket === 'new') return null;
  if (bucket === 'in_progress' && item.status === 'NEW') return 'IN_REVIEW';
  if (bucket === 'done') {
    const type = item.request_type;
    if (type === 'OTHER' && (item.status === 'IN_REVIEW' || item.status === 'WAITING_FOR_CUSTOMER')) {
      return 'COMPLETED';
    }
    if (type === 'APPOINTMENT' && item.status === 'CONFIRMED') return 'COMPLETED';
    if (type === 'ORDER' && item.status === 'READY') return 'COMPLETED';
  }
  return null;
}

export function formatRequestWhen(iso: string | null | undefined, locale: string): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const loc = locale.startsWith('ar') ? 'ar' : locale.startsWith('fr') ? 'fr' : 'en';
  const now = new Date();
  const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startMsg = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const dayDiff = Math.round((startToday.getTime() - startMsg.getTime()) / 86_400_000);
  const time = d.toLocaleTimeString(loc, { hour: 'numeric', minute: '2-digit' });
  if (dayDiff === 0) return loc === 'en' ? `Today, ${time}` : time;
  if (dayDiff === 1) return loc === 'en' ? `Yesterday, ${time}` : time;
  const date = d.toLocaleDateString(loc, { month: 'short', day: 'numeric' });
  return `${date}, ${time}`;
}

export function formatShortDate(ymd: string, locale: string): string {
  const d = new Date(`${ymd.slice(0, 10)}T12:00:00`);
  if (Number.isNaN(d.getTime())) return ymd;
  const loc = locale.startsWith('ar') ? 'ar' : locale.startsWith('fr') ? 'fr' : 'en-US';
  return d.toLocaleDateString(loc, { month: 'short', day: 'numeric', year: 'numeric' });
}

export function startOfDayIso(ymd: string): string {
  return new Date(`${ymd.slice(0, 10)}T00:00:00`).toISOString();
}

export function endOfDayIso(ymd: string): string {
  return new Date(`${ymd.slice(0, 10)}T23:59:59.999`).toISOString();
}

export function formatPhone(raw: string | null | undefined): string {
  const digits = String(raw || '').replace(/[^\d+]/g, '');
  if (!digits) return '';
  const m = digits.match(/^\+?(\d{3})(\d{2})(\d{3})(\d{3})$/);
  if (m) return `+${m[1]} ${m[2]} ${m[3]} ${m[4]}`;
  return digits.startsWith('+') ? digits : `+${digits}`;
}

function formatItems(items: unknown): string {
  if (!items) return '';
  if (typeof items === 'string') return items.trim();
  if (!Array.isArray(items)) return '';
  return items
    .map((entry) => {
      if (typeof entry === 'string') return entry;
      if (!entry || typeof entry !== 'object') return '';
      const rec = entry as Record<string, unknown>;
      const name = String(rec.name || rec.title || rec.item || rec.service || '').trim();
      const qty = rec.qty ?? rec.quantity ?? rec.count;
      if (name && qty != null && String(qty) !== '1') return `${qty} ${name}`;
      if (name && qty != null) return `${name} ×${qty}`;
      return name;
    })
    .filter(Boolean)
    .join(', ');
}

function formatApptWhen(dateStr: string | null | undefined, timeStr: string | null | undefined): string {
  const date = String(dateStr || '').trim();
  const time = String(timeStr || '').trim();
  if (date && time) return `${date} at ${time}`;
  return date || time;
}

export function cardSummary(card: RequestCard): string {
  const done = card.status === 'COMPLETED';
  const items = formatItems(card.requested_items);
  const branch = String(card.requested_branch || '').trim();
  const when = formatApptWhen(card.preferred_date, card.preferred_time);
  if (card.request_type === 'APPOINTMENT') {
    const head = done ? 'Appointment completed' : 'Appointment confirmed';
    const bits = [when, branch].filter(Boolean).join(', ');
    if (bits) return `${head}: ${bits}.`;
    if (card.title) return `${head}: ${card.title}`;
    return `${head}.`;
  }
  if (card.request_type === 'ORDER') {
    const head = done ? 'Order completed' : 'Order confirmed';
    const body = items || String(card.title || '').trim();
    if (body) return `${head}: ${body}.`;
    return `${head}.`;
  }
  return String(card.title || card.customer_notes || '').trim();
}

export function formatPrintSlip(detail: RequestDetail, phone?: string | null): string {
  const lines = [
    `Request #${detail.request_number}`,
    detail.customer_display_name || detail.customer_name || '',
    phone || '',
    cardSummary(detail),
    detail.delivery_address ? `Address: ${detail.delivery_address}` : '',
    detail.customer_notes ? `Notes: ${detail.customer_notes}` : '',
  ];
  return lines.filter(Boolean).join('\n');
}

export function assigneeFirstName(raw: string | null | undefined): string {
  const value = String(raw || '').trim();
  if (!value) return '';
  const local = value.includes('@') ? value.split('@')[0] : value;
  const token = local.split(/[\s._-]+/).filter(Boolean)[0] || local;
  return token.charAt(0).toUpperCase() + token.slice(1);
}
