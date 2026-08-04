import CmSectionShell from "./CmSectionShell";
import { useCmSectionDraft } from "./useCmSectionDraft";

const FIELD_CLASS = "w-full rounded-xl border border-slate-200 px-3 py-2 text-sm";

/**
 * Owner-friendly AI Basics form (no JSON).
 */
const CmAiBasicsPage = () => {
  const draft = useCmSectionDraft("ai_basics");
  const p = draft.payload;

  /**
   * @param {string} key
   * @param {string} value
   */
  const setField = (key, value) => {
    draft.setPayload({ ...p, [key]: value });
  };

  return (
    <CmSectionShell
      title="AI Basics"
      description="Clinic identity and persona the AI uses. Locked security and channel rules stay in code and are not editable here."
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
      <div className="rounded-2xl border border-slate-200 bg-white p-5 space-y-4 max-w-3xl">
        <label className="block space-y-1">
          <span className="text-sm font-medium text-slate-800">AI display name</span>
          <input
            className={FIELD_CLASS}
            value={String(p.assistant_name || "")}
            onChange={(e) => setField("assistant_name", e.target.value)}
          />
        </label>
        <label className="block space-y-1">
          <span className="text-sm font-medium text-slate-800">Business name</span>
          <input
            className={FIELD_CLASS}
            value={String(p.clinic_name || "")}
            onChange={(e) => setField("clinic_name", e.target.value)}
          />
        </label>
        <label className="block space-y-1">
          <span className="text-sm font-medium text-slate-800">AI role</span>
          <input
            className={FIELD_CLASS}
            value={String(p.ai_role || "")}
            onChange={(e) => setField("ai_role", e.target.value)}
            placeholder="e.g. Friendly clinic assistant for laser hair removal"
          />
        </label>
        <label className="block space-y-1">
          <span className="text-sm font-medium text-slate-800">Business purpose</span>
          <textarea
            className={FIELD_CLASS}
            rows={2}
            value={String(p.business_purpose || "")}
            onChange={(e) => setField("business_purpose", e.target.value)}
          />
        </label>
        <label className="block space-y-1">
          <span className="text-sm font-medium text-slate-800">Short introduction</span>
          <textarea
            className={FIELD_CLASS}
            rows={2}
            value={String(p.short_introduction || "")}
            onChange={(e) => setField("short_introduction", e.target.value)}
          />
        </label>
        <label className="block space-y-1">
          <span className="text-sm font-medium text-slate-800">Greeting behavior</span>
          <textarea
            className={FIELD_CLASS}
            rows={2}
            value={String(p.greeting_behavior || "")}
            onChange={(e) => setField("greeting_behavior", e.target.value)}
          />
        </label>
        <label className="block space-y-1">
          <span className="text-sm font-medium text-slate-800">Core business description</span>
          <textarea
            className={FIELD_CLASS}
            rows={4}
            value={String(p.identity_summary || "")}
            onChange={(e) => setField("identity_summary", e.target.value)}
          />
        </label>
        <label className="block space-y-1">
          <span className="text-sm font-medium text-slate-800">Additional owner instructions</span>
          <textarea
            className={FIELD_CLASS}
            rows={4}
            value={String(p.advanced_instructions || "")}
            onChange={(e) => setField("advanced_instructions", e.target.value)}
          />
          <span className="text-xs text-slate-500">
            Business guidance only. Cannot override prices, hours, contacts, or restricted topics.
          </span>
        </label>
        <label className="block space-y-1">
          <span className="text-sm font-medium text-slate-800">Notes / legacy prompt archive</span>
          <textarea
            className={FIELD_CLASS}
            rows={4}
            value={String(p.notes || "")}
            onChange={(e) => setField("notes", e.target.value)}
          />
        </label>
      </div>
    </CmSectionShell>
  );
};

export default CmAiBasicsPage;
