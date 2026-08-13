export type DashboardPeriodSelection =
  | { kind: 'preset'; id: 'billing' | '7d' | '30d' }
  | { kind: 'custom'; start: string; end: string };

export function monthStartIso(date = new Date()): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  return `${y}-${m}-01`;
}

export function todayIso(date = new Date()): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

export function formatDashboardRangeLabel(
  startIso: string,
  endIso: string,
  locale: string,
): string {
  const start = new Date(`${startIso.slice(0, 10)}T12:00:00`);
  const end = new Date(`${endIso.slice(0, 10)}T12:00:00`);
  const fmt = new Intl.DateTimeFormat(locale, { month: 'short', day: 'numeric' });
  return `${fmt.format(start)} – ${fmt.format(end)}`;
}

export function formatRenewDate(iso: string | null | undefined, locale: string): string | null {
  if (!iso) return null;
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) return null;
  return new Intl.DateTimeFormat(locale, { month: 'short', day: 'numeric' }).format(dt);
}

export function formatCount(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return '—';
  return n.toLocaleString();
}
