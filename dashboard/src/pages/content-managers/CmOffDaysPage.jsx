import CmSectionShell from "./CmSectionShell";
import { useCmSectionDraft } from "./useCmSectionDraft";

const FIELD = "w-full rounded-xl border border-slate-200 px-3 py-2 text-sm";
const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

const CmOffDaysPage = () => {
  const draft = useCmSectionDraft("off_days");
  const p = draft.payload;
  const rules = Array.isArray(p.rules) ? p.rules : [];

  const addWeekly = () => {
    draft.setPayload({
      ...p,
      rules: [
        ...rules,
        { id: `weekly_${Date.now()}`, kind: "weekly", weekday: 4, date: "", start_date: "", end_date: "", reason: "" },
      ],
    });
  };

  const addDate = () => {
    draft.setPayload({
      ...p,
      rules: [
        ...rules,
        { id: `date_${Date.now()}`, kind: "date", weekday: null, date: "", start_date: "", end_date: "", reason: "" },
      ],
    });
  };

  /**
   * @param {number} index
   * @param {Record<string, unknown>} patch
   */
  const updateRule = (index, patch) => {
    const next = rules.map((rule, i) => (i === index ? { ...rule, ...patch } : rule));
    draft.setPayload({ ...p, rules: next });
  };

  /**
   * @param {number} index
   */
  const removeRule = (index) => {
    draft.setPayload({ ...p, rules: rules.filter((_, i) => i !== index) });
  };

  return (
    <CmSectionShell
      title="Off Days"
      description="Weekly closed days and specific dates. The AI uses this for availability answers after publish."
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
        <label className="block space-y-1 max-w-md">
          <span className="text-sm font-medium">Timezone</span>
          <input
            className={FIELD}
            value={String(p.timezone || "Asia/Beirut")}
            onChange={(e) => draft.setPayload({ ...p, timezone: e.target.value })}
          />
        </label>

        <div className="flex gap-2">
          <button type="button" className="rounded-xl bg-slate-900 text-white px-3 py-2 text-sm" onClick={addWeekly}>
            Add weekly off day
          </button>
          <button type="button" className="rounded-xl border border-slate-300 px-3 py-2 text-sm" onClick={addDate}>
            Add specific date
          </button>
        </div>

        {rules.map((rule, index) => (
          <div key={String(rule.id)} className="rounded-2xl border border-slate-200 bg-white p-4 space-y-2">
            <div className="flex justify-between text-sm font-medium">
              <span>{String(rule.kind)}</span>
              <button type="button" className="text-red-600" onClick={() => removeRule(index)}>
                Remove
              </button>
            </div>
            {rule.kind === "weekly" ? (
              <select
                className={FIELD}
                value={Number(rule.weekday ?? 4)}
                onChange={(e) => updateRule(index, { weekday: Number(e.target.value) })}
              >
                {WEEKDAYS.map((label, weekday) => (
                  <option key={label} value={weekday}>
                    {label}
                  </option>
                ))}
              </select>
            ) : (
              <input
                type="date"
                className={FIELD}
                value={String(rule.date || "")}
                onChange={(e) => updateRule(index, { date: e.target.value })}
              />
            )}
            <input
              className={FIELD}
              placeholder="Reason / note"
              value={String(rule.reason || "")}
              onChange={(e) => updateRule(index, { reason: e.target.value })}
            />
          </div>
        ))}
      </div>
    </CmSectionShell>
  );
};

export default CmOffDaysPage;
