export type DashboardPresetId =
  | 'all_time'
  | 'today'
  | 'last_7d'
  | 'last_month'
  | 'last_6m'
  | 'last_year';

export type DashboardPeriodSelection =
  | { kind: 'preset'; id: DashboardPresetId }
  | { kind: 'custom'; start: string; end: string };

export type DashboardNamedApiPeriod = 'today' | '7d' | 'last_month';

export const DEFAULT_DASHBOARD_PERIOD: DashboardPeriodSelection = { kind: 'preset', id: 'all_time' };

const NAMED_API_PERIODS: Partial<Record<DashboardPresetId, DashboardNamedApiPeriod>> = {
  today: 'today',
  last_7d: '7d',
  last_month: 'last_month',
};

export function isAllTimePeriod(period: DashboardPeriodSelection): boolean {
  return period.kind === 'preset' && period.id === 'all_time';
}

/** Stable cache key so dashboard data never bleeds across date ranges. */
export function dashboardPeriodKey(period: DashboardPeriodSelection): string {
  if (period.kind === 'custom') return `custom:${period.start}:${period.end}`;
  return `preset:${period.id}`;
}

export function namedDashboardApiPeriod(
  period: DashboardPeriodSelection,
): DashboardNamedApiPeriod | null {
  if (period.kind !== 'preset') return null;
  return NAMED_API_PERIODS[period.id] ?? null;
}

export function ymdFromDate(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

export function monthStartIso(date = new Date()): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  return `${y}-${m}-01`;
}

export function todayIso(date = new Date()): string {
  return ymdFromDate(date);
}

/** Previous complete local calendar month (not a rolling 30 days, not UTC). */
export function lastCalendarMonthRange(date = new Date()): { start: string; end: string } {
  const start = new Date(date.getFullYear(), date.getMonth() - 1, 1);
  const end = new Date(date.getFullYear(), date.getMonth(), 0);
  return { start: ymdFromDate(start), end: ymdFromDate(end) };
}

/** Rolling 7 local calendar days including today (today and the previous 6). */
export function lastSevenDaysRange(date = new Date()): { start: string; end: string } {
  const end = todayIso(date);
  const start = new Date(date.getFullYear(), date.getMonth(), date.getDate() - 6);
  return { start: ymdFromDate(start), end };
}

export function resolvePresetRange(
  id: DashboardPresetId,
  date = new Date(),
): { start: string; end: string } {
  const end = todayIso(date);
  if (id === 'all_time') return { start: '1970-01-01', end }; // existing custom window; API has no `all` period
  if (id === 'today') {
    // Inclusive local calendar day. Queries use period=today (tz), not this pair as exclusive end.
    return { start: end, end };
  }
  if (id === 'last_7d') return lastSevenDaysRange(date);
  if (id === 'last_month') return lastCalendarMonthRange(date);
  if (id === 'last_6m') {
    const start = new Date(date.getFullYear(), date.getMonth() - 6, 1);
    return { start: ymdFromDate(start), end };
  }
  const start = new Date(date.getFullYear(), date.getMonth() - 12, 1);
  return { start: ymdFromDate(start), end };
}

export function dashboardQueryRange(
  period: DashboardPeriodSelection,
  date = new Date(),
): { start: string; end: string } {
  if (period.kind === 'custom') return { start: period.start, end: period.end };
  return resolvePresetRange(period.id, date);
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
