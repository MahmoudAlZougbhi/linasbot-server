import CmSectionShell from "./CmSectionShell";
import { useCmSectionDraft } from "./useCmSectionDraft";

const FIELD = "w-full rounded-full bg-slate-100 px-3 py-2 text-sm";

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
      title="Customer AI Limits"
      description="Protect credits by limiting each customer’s AI usage."
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
      <p className="mb-4 rounded-xl bg-teal-50 px-4 py-3 text-sm text-teal-800">
        Applied separately to every customer across all connected channels.
      </p>
      <div className="space-y-4 max-w-xl">
        <div className="rounded-2xl border border-slate-200 bg-white p-5 space-y-3">
          <h3 className="text-sm font-semibold text-slate-800">Text & Chat</h3>
          <label className="block space-y-1">
            <span className="text-sm">Read per message</span>
            <input
              type="number"
              min={0}
              className={FIELD}
              value={Number(p.text_words_per_message ?? 500)}
              onChange={(e) => setField("text_words_per_message", Number(e.target.value))}
            />
          </label>
          <p className="text-sm">AI replies per customer</p>
          {/** @type {Array<[string, string]>} */ ([
            ["text_replies_per_day", "Day"],
            ["text_replies_per_week", "Week"],
            ["text_replies_per_month", "Month"],
          ]).map(([key, label]) => (
            <label key={key} className="block space-y-1">
              <span className="text-xs text-slate-500">{label}</span>
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
        <div className="rounded-2xl border border-slate-200 bg-white p-5 space-y-3">
          <h3 className="text-sm font-semibold text-slate-800">Photos</h3>
          <label className="block space-y-1">
            <span className="text-sm">Photos per message</span>
            <input
              type="number"
              min={0}
              className={FIELD}
              value={Number(p.photos_per_message ?? 2)}
              onChange={(e) => setField("photos_per_message", Number(e.target.value))}
            />
          </label>
          <p className="text-sm">Analyses per customer</p>
          {/** @type {Array<[string, string]>} */ ([
            ["image_per_day", "Day"],
            ["image_per_week", "Week"],
            ["image_per_month", "Month"],
          ]).map(([key, label]) => (
            <label key={key} className="block space-y-1">
              <span className="text-xs text-slate-500">{label}</span>
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
        <div className="rounded-2xl border border-slate-200 bg-white p-5 space-y-3">
          <h3 className="text-sm font-semibold text-slate-800">Voice</h3>
          <label className="block space-y-1">
            <span className="text-sm">Minutes per message</span>
            <input
              type="number"
              min={0}
              className={FIELD}
              value={Number(p.voice_minutes_per_message ?? 2)}
              onChange={(e) => setField("voice_minutes_per_message", Number(e.target.value))}
            />
          </label>
          <p className="text-sm">Minutes per customer</p>
          {/** @type {Array<[string, string]>} */ ([
            ["voice_minutes_per_day", "Day"],
            ["voice_minutes_per_week", "Week"],
            ["voice_minutes_per_month", "Month"],
          ]).map(([key, label]) => (
            <label key={key} className="block space-y-1">
              <span className="text-xs text-slate-500">{label}</span>
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
        <p className="rounded-xl bg-teal-50 px-4 py-3 text-sm text-teal-800">
          <strong>Automatic limit messages.</strong> Linas explains which limit was reached and when it
          resets. Long content is processed only up to the allowed amount.
        </p>
      </div>
    </CmSectionShell>
  );
};

export default CmAiLimitsPage;
