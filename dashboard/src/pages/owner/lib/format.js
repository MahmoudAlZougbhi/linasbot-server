// @ts-nocheck
/** @param {unknown} value */
function asDate(value) {
  if (value == null || value === '' || value === 0 || value === '0') return null;
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value;
  if (typeof value === 'number') {
    const ms = value < 1e11 ? value * 1000 : value;
    const date = new Date(ms);
    return Number.isNaN(date.getTime()) ? null : date;
  }
  const text = String(value).trim();
  if (!text) return null;
  if (/^\d+(\.\d+)?$/.test(text)) return asDate(Number(text));
  const iso = text.replace(/(\.\d{3})\d+/, '$1');
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? null : date;
}

function cairo(value, withDate) {
  const date = asDate(value);
  if (!date) return '—';
  const formatted = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Africa/Cairo',
    month: withDate ? 'short' : undefined,
    day: withDate ? 'numeric' : undefined,
    year: withDate ? 'numeric' : undefined,
    hour: 'numeric',
    minute: '2-digit',
    second: withDate ? undefined : '2-digit',
  }).format(date);
  return formatted.replace(/[\u202F\u00A0]/g, ' ');
}

/** @param {unknown} value */
export function formatNumber(value) {
  if (value == null || value === '') return '—';
  const number = Number(value);
  if (!Number.isFinite(number)) return '—';
  return new Intl.NumberFormat('en-US').format(number);
}

/** @param {unknown} value */
export function formatUsd(value) {
  if (value == null || value === '') return '—';
  const number = Number(value);
  if (!Number.isFinite(number)) return '—';
  if (number === 0) return '$0';
  if (Math.abs(number) < 1) {
    const text = number.toFixed(4).replace(/0+$/, '').replace(/\.$/, '');
    return `$${text}`;
  }
  if (Number.isInteger(number)) return `$${formatNumber(number)}`;
  return `$${number.toFixed(2)}`;
}

/** @param {unknown} value */
export function formatDateTime(value) {
  return cairo(value, true);
}

/** @param {unknown} value */
export function formatTime(value) {
  return cairo(value, false);
}

/** @param {unknown} value @param {number} [now] */
export function formatRelative(value, now = Date.now()) {
  const date = asDate(value);
  if (!date) return '—';
  const delta = Math.max(0, now - date.getTime());
  const minutes = Math.floor(delta / 60000);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  return formatDateTime(date);
}

/** @param {{ business_name?: string, tenant_id?: string, email?: string } | null | undefined} row */
export function businessDisplayName(row) {
  const name = String(row?.business_name || '').trim();
  if (name && !name.includes('@')) return name;
  const id = String(row?.tenant_id || '').trim();
  if (id) {
    return id.split(/[-_]+/).filter(Boolean).map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(' ');
  }
  return String(row?.email || '');
}

/** @param {unknown} ms */
export function formatDuration(ms) {
  const number = Number(ms);
  if (!Number.isFinite(number) || number <= 0) return '';
  if (number < 1000) return `${Math.round(number)} ms`;
  if (number < 60000) return `${(number / 1000).toFixed(1)} s`;
  const minutes = Math.floor(number / 60000);
  const seconds = Math.round((number % 60000) / 1000);
  return `${minutes} min ${seconds} s`;
}

/** @param {unknown} value */
export function formatPercent(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '—';
  return `${Math.round(number * 100)}%`;
}
