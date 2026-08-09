import CmSectionShell from "./CmSectionShell";
import { useCmSectionDraft } from "./useCmSectionDraft";

const FIELD = "w-full rounded-xl border border-slate-200 px-3 py-2 text-sm";
const DAYS = [
  { key: "monday", label: "Monday" },
  { key: "tuesday", label: "Tuesday" },
  { key: "wednesday", label: "Wednesday" },
  { key: "thursday", label: "Thursday" },
  { key: "friday", label: "Friday" },
  { key: "saturday", label: "Saturday" },
  { key: "sunday", label: "Sunday" },
];

function emptyDay() {
  return { closed: false, open: "09:00", close: "18:00" };
}

function emptySchedule() {
  return {
    id: `hours_${Date.now()}`,
    title: "",
    monday: emptyDay(),
    tuesday: emptyDay(),
    wednesday: emptyDay(),
    thursday: emptyDay(),
    friday: emptyDay(),
    saturday: { closed: true, open: "", close: "" },
    sunday: { closed: true, open: "", close: "" },
    notes: null,
  };
}

const CmOpeningHoursPage = () => {
  const draft = useCmSectionDraft("opening_hours");
  const p = draft.payload;
  const items = Array.isArray(p.items) ? p.items : [];

  const add = () => {
    draft.setPayload({ ...p, items: [emptySchedule(), ...items] });
  };

  /**
   * @param {number} index
   * @param {Record<string, unknown>} patch
   */
  const updateItem = (index, patch) => {
    const next = items.map((item, i) => (i === index ? { ...item, ...patch } : item));
    draft.setPayload({ ...p, items: next });
  };

  /**
   * @param {number} index
   * @param {string} dayKey
   * @param {Record<string, unknown>} dayPatch
   */
  const updateDay = (index, dayKey, dayPatch) => {
    const item = items[index] || {};
    const day = { ...(item[dayKey] || {}), ...dayPatch };
    updateItem(index, { [dayKey]: day });
  };

  /**
   * @param {number} index
   */
  const removeItem = (index) => {
    draft.setPayload({ ...p, items: items.filter((_, i) => i !== index) });
  };

  return (
    <CmSectionShell
      title="Opening Hours"
      description="Named calendars (Men / Women / Branch). Each weekday is open from→to or marked off."
      loading={draft.loading}
      dirty={draft.dirty}
      saving={draft.saving}
      validating={draft.validating}
      conflict={draft.conflict}
      meta={draft.meta}
      validation={draft.validation}
      onReload={() => void draft.load()}
      onSave={() => void draft.save()}
      onValidate={() => void draft.validate()}
    >
      <div className="space-y-4 max-w-3xl">
        <button type="button" className="rounded-xl bg-slate-900 text-white px-3 py-2 text-sm" onClick={add}>
          Add hours calendar
        </button>
        {items.map((item, index) => (
          <div key={String(item.id)} className="rounded-2xl border border-slate-200 bg-white p-4 space-y-3">
            <div className="flex justify-between gap-3">
              <input
                className={FIELD}
                placeholder="Title (e.g. Men / Branch Beirut)"
                value={String(item.title || "")}
                onChange={(e) => updateItem(index, { title: e.target.value })}
              />
              <button type="button" className="text-red-600 text-sm shrink-0" onClick={() => removeItem(index)}>
                Remove
              </button>
            </div>
            {DAYS.map((day) => {
              const row = item[day.key] || {};
              const closed = Boolean(row.closed);
              return (
                <div key={day.key} className="grid grid-cols-[120px_80px_1fr_1fr] gap-2 items-center">
                  <span className="text-sm font-medium">{day.label}</span>
                  <button
                    type="button"
                    className="rounded-lg border border-slate-300 px-2 py-1 text-xs"
                    onClick={() =>
                      updateDay(index, day.key, {
                        closed: !closed,
                        open: closed ? row.open || "09:00" : "",
                        close: closed ? row.close || "18:00" : "",
                      })
                    }
                  >
                    {closed ? "Off" : "Open"}
                  </button>
                  {!closed ? (
                    <>
                      <input
                        className={FIELD}
                        placeholder="From"
                        value={String(row.open || "")}
                        onChange={(e) => updateDay(index, day.key, { open: e.target.value })}
                      />
                      <input
                        className={FIELD}
                        placeholder="To"
                        value={String(row.close || "")}
                        onChange={(e) => updateDay(index, day.key, { close: e.target.value })}
                      />
                    </>
                  ) : (
                    <>
                      <span className="text-slate-400 text-sm col-span-2">Closed</span>
                    </>
                  )}
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </CmSectionShell>
  );
};

export default CmOpeningHoursPage;
