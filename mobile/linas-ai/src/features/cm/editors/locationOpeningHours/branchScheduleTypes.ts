export const WEEKDAY_KEYS = [
  'monday',
  'tuesday',
  'wednesday',
  'thursday',
  'friday',
  'saturday',
  'sunday',
] as const;

export type WeekdayKey = (typeof WEEKDAY_KEYS)[number];

export type BranchDaySchedule = {
  enabled: boolean;
  open: string;
  close: string;
  off_day: boolean;
  note: string | null;
};

export type WeeklySchedule = Record<WeekdayKey, BranchDaySchedule>;

export function emptyBranchDay(): BranchDaySchedule {
  return { enabled: false, open: '', close: '', off_day: false, note: null };
}

export function emptyWeeklySchedule(): WeeklySchedule {
  return {
    monday: emptyBranchDay(),
    tuesday: emptyBranchDay(),
    wednesday: emptyBranchDay(),
    thursday: emptyBranchDay(),
    friday: emptyBranchDay(),
    saturday: emptyBranchDay(),
    sunday: emptyBranchDay(),
  };
}
