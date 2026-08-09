import CmSectionShell from "./CmSectionShell";
import { useCmSectionDraft } from "./useCmSectionDraft";

const FIELD = "w-full rounded-xl border border-slate-200 px-3 py-2 text-sm";

const CmAiLimitsPage = () => {
  const draft = useCmSectionDraft("ai_limits");
  const p = draft.payload;

  /**
   * @param {string} key
   * @param {string | number | boolean} value
   */
  const setField = (key, value) => draft.setPayload({ ...p, [key]: value });

  return (
    <CmSectionShell
      title="AI Limits"
      description="Per-customer usage limits for this business. Absolute platform clamps still apply in code."
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
      <div className="space-y-4 max-w-xl rounded-2xl border border-slate-200 bg-white p-5">
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={Boolean(p.unlimited)} onChange={(e) => setField("unlimited", e.target.checked)} />
          Unlimited (disable enforcement)
        </label>
        {/** @type {Array<[string, string]>} */ ([
          ["image_per_day", "Images per day"],
          ["image_per_week", "Images per week"],
          ["context_lines_per_day", "Context lines per day"],
          ["context_lines_per_week", "Context lines per week"],
        ]).map(([key, label]) => (
          <label key={key} className="block space-y-1">
            <span className="text-sm font-medium">{label}</span>
            <input
              type="number"
              min={0}
              className={FIELD}
              value={Number(p[key] ?? 0)}
              onChange={(e) => setField(key, Number(e.target.value))}
            />
          </label>
        ))}
      </div>
    </CmSectionShell>
  );
};

export default CmAiLimitsPage;
