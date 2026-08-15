import { asRecord } from '../../cmApi';
import {
  emptyBranchDay,
  emptyWeeklySchedule,
  type BranchDaySchedule,
  type WeeklySchedule,
  WEEKDAY_KEYS,
} from './branchScheduleTypes';

export function normalizeWeeklySchedule(raw: unknown): WeeklySchedule {
  const src = asRecord(raw);
  const out = emptyWeeklySchedule();
  for (const day of WEEKDAY_KEYS) {
    const row = asRecord(src[day]);
    out[day] = {
      enabled: Boolean(row.enabled),
      open: String(row.open || ''),
      close: String(row.close || ''),
      off_day: Boolean(row.off_day),
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
  };
}
