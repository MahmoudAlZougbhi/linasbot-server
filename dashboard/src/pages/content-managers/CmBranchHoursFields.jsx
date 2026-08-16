import { asRecord } from "./cmDraftHelpers";

const DAYS = [
  { key: "monday", label: "Monday" },
  { key: "tuesday", label: "Tuesday" },
  { key: "wednesday", label: "Wednesday" },
  { key: "thursday", label: "Thursday" },
  { key: "friday", label: "Friday" },
  { key: "saturday", label: "Saturday" },
  { key: "sunday", label: "Sunday" },
];

const FIELD_CLASS = "w-full rounded-xl border border-slate-200 px-3 py-2 text-sm";

export function emptyHours() {
  return {
    monday: "",
    tuesday: "",
    wednesday: "",
    thursday: "",
    friday: "",
    saturday: "",
    sunday: "",
    summary: "",
  };
}

export function emptyBranchDay() {
  return { enabled: false, open: "", close: "", off_day: false, note: null };
}

export function emptyWeeklySchedule() {
  return Object.fromEntries(DAYS.map((day) => [day.key, emptyBranchDay()]));
}

/**
 * @param {unknown} raw
 */
export function normalizeWeeklySchedule(raw) {
  const src = asRecord(raw);
  const out = emptyWeeklySchedule();
  for (const day of DAYS) {
    const row = asRecord(src[day.key]);
    out[day.key] = {
      enabled: Boolean(row.enabled),
      open: String(row.open || ""),
      close: String(row.close || ""),
      off_day: Boolean(row.off_day),
      note: row.note == null ? null : String(row.note),
    };
  }
  return out;
}

/**
 * @param {{
 *   schedule: Record<string, { enabled: boolean, open: string, close: string, off_day: boolean, note: string | null }>;
 *   onChange: (next: Record<string, unknown>) => void;
 * }} props
 */
export function CmBranchHoursFields({ schedule, onChange }) {
  const rows = normalizeWeeklySchedule(schedule);

  /**
   * @param {string} dayKey
   * @param {Record<string, unknown>} patch
   */
  const patchDay = (dayKey, patch) => {
    onChange({ ...rows, [dayKey]: { ...rows[dayKey], ...patch } });
  };

  return (
    <div className="rounded-xl border border-slate-200 divide-y">
      {DAYS.map((day) => {
        const row = rows[day.key];
        const off = Boolean(row.enabled && row.off_day);
        return (
          <div key={day.key} className="grid grid-cols-[110px_1fr_auto] gap-2 items-center p-2">
            <span className="text-sm font-medium">{day.label}</span>
            {off ? (
              <span className="text-sm text-orange-600">Day off</span>
            ) : (
              <div className="flex gap-2">
                <input
                  className={FIELD_CLASS}
                  value={String(row.open || "")}
                  placeholder="09:00"
                  onChange={(e) =>
                    patchDay(day.key, { enabled: true, off_day: false, open: e.target.value })
                  }
                />
                <input
                  className={FIELD_CLASS}
                  value={String(row.close || "")}
                  placeholder="20:00"
                  onChange={(e) =>
                    patchDay(day.key, { enabled: true, off_day: false, close: e.target.value })
                  }
                />
              </div>
            )}
            <button
              type="button"
              className={`rounded-lg border px-2 py-1 text-xs ${off ? "border-orange-300 text-orange-700" : "border-emerald-300 text-emerald-700"}`}
              onClick={() =>
                patchDay(
                  day.key,
                  off
                    ? { enabled: true, off_day: false, open: row.open || "09:00", close: row.close || "20:00" }
                    : { enabled: true, off_day: true, open: "", close: "" },
                )
              }
            >
              {off ? "Day off" : "Open"}
            </button>
          </div>
        );
      })}
    </div>
  );
}
