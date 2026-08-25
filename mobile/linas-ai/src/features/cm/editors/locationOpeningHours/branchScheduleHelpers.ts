import {
  emptyWeeklySchedule,
  type BranchDaySchedule,
  type WeekdayKey,
  type WeeklySchedule,
  WEEKDAY_KEYS,
} from './branchScheduleTypes';

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function asRecordList(value: unknown): Record<string, unknown>[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is Record<string, unknown> => !!item && typeof item === 'object');
}

export const DEFAULT_OPEN = '09:00';
export const DEFAULT_CLOSE = '20:00';

const JS_DAY_TO_KEY: WeekdayKey[] = [
  'sunday',
  'monday',
  'tuesday',
  'wednesday',
  'thursday',
  'friday',
  'saturday',
];

export function normalizeWeeklySchedule(raw: unknown): WeeklySchedule {
  const src = asRecord(raw);
  const out = emptyWeeklySchedule();
  for (const day of WEEKDAY_KEYS) {
    const row = asRecord(src[day]);
    const open = String(row.open || '');
    const close = String(row.close || '');
    const offDay = Boolean(row.off_day);
    let enabled = Boolean(row.enabled);
    if (!enabled && (offDay || (open.trim() && close.trim()))) {
      enabled = true;
    }
    out[day] = {
      enabled,
      open,
      close,
      off_day: offDay,
      note: row.note == null ? null : String(row.note),
    };
  }
  return out;
}

export function patchWeeklyDay(
  schedule: WeeklySchedule,
  dayKey: keyof WeeklySchedule,
  patch: Partial<BranchDaySchedule>,
): WeeklySchedule {
  return { ...schedule, [dayKey]: { ...schedule[dayKey], ...patch } };
}

export function applyScheduleToDays(
  schedule: WeeklySchedule,
  days: WeekdayKey[],
  patch: Partial<BranchDaySchedule>,
): WeeklySchedule {
  let next = schedule;
  for (const day of days) {
    next = patchWeeklyDay(next, day, patch);
  }
  return next;
}

export function openDayPatch(open = DEFAULT_OPEN, close = DEFAULT_CLOSE): BranchDaySchedule {
  return { enabled: true, off_day: false, open, close, note: null };
}

export function dayOffPatch(): BranchDaySchedule {
  return { enabled: true, off_day: true, open: '', close: '', note: null };
}

export function newBranchRecord(id: string): Record<string, unknown> {
  return {
    id,
    labels: { en: '', ar: '', fr: '', franco: '' },
    address: '',
    street: '',
    building: '',
    floor: '',
    country: '',
    maps_url: '',
    hours: {},
    weekly_schedule: emptyWeeklySchedule(),
    available: true,
    notes: null,
    attachments: [],
  };
}

export function branchAddress(branch: Record<string, unknown>): string {
  const parts = [branch.street, branch.building, branch.floor, branch.country]
    .map((p) => String(p || '').trim())
    .filter(Boolean);
  if (parts.length) return parts.join(', ');
  return String(branch.address || '');
}

export function hoursAreSet(schedule: WeeklySchedule): boolean {
  return WEEKDAY_KEYS.some((key) => schedule[key].enabled);
}

export function todayWeekdayKey(now = new Date()): WeekdayKey {
  return JS_DAY_TO_KEY[now.getDay()] ?? 'monday';
}

export type TodayStatus =
  | { kind: 'none' }
  | { kind: 'open'; open: string; close: string }
  | { kind: 'closed' };

export function todayStatus(schedule: WeeklySchedule, now = new Date()): TodayStatus {
  if (!hoursAreSet(schedule)) return { kind: 'none' };
  const day = schedule[todayWeekdayKey(now)];
  if (day.enabled && !day.off_day && day.open.trim() && day.close.trim()) {
    return { kind: 'open', open: day.open, close: day.close };
  }
  return { kind: 'closed' };
}

export function formatClock12(hhmm: string): string {
  const m = /^(\d{1,2}):(\d{2})$/.exec(String(hhmm || '').trim());
  if (!m) return '';
  let hour = Number(m[1]);
  if (!Number.isFinite(hour) || hour < 0 || hour > 23) return '';
  const min = m[2];
  const suffix = hour < 12 ? 'AM' : 'PM';
  if (hour === 0) hour = 12;
  else if (hour > 12) hour -= 12;
  return `${hour}:${min} ${suffix}`;
}

export function parseClock12(display: string): string {
  const raw = String(display || '')
    .trim()
    .toUpperCase()
    .replace(/\s+/g, ' ');
  if (!raw) return '';
  let m = /^(\d{1,2}):(\d{2})\s*(AM|PM)$/.exec(raw);
  if (m) {
    let hour = Number(m[1]);
    const min = Number(m[2]);
    const ampm = m[3];
    if (hour < 1 || hour > 12 || min < 0 || min > 59) return '';
    if (ampm === 'AM') {
      if (hour === 12) hour = 0;
    } else if (hour !== 12) {
      hour += 12;
    }
    return `${String(hour).padStart(2, '0')}:${String(min).padStart(2, '0')}`;
  }
  m = /^(\d{1,2}):(\d{2})$/.exec(raw);
  if (!m) return '';
  const hour = Number(m[1]);
  const min = Number(m[2]);
  if (hour < 0 || hour > 23 || min < 0 || min > 59) return '';
  return `${String(hour).padStart(2, '0')}:${String(min).padStart(2, '0')}`;
}

export function branchMediaCount(branch: Record<string, unknown>): number {
  const attachments = asRecordList(branch.attachments);
  const maps = String(branch.maps_url || '').trim();
  return attachments.length + (maps ? 1 : 0);
}

export function matchesBranchQuery(branch: Record<string, unknown>, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  const labels = asRecord(branch.labels);
  const name = [labels.en, labels.ar, labels.fr, labels.franco]
    .map((v) => String(v || '').toLowerCase())
    .join(' ');
  const address = branchAddress(branch).toLowerCase();
  return name.includes(q) || address.includes(q);
}
