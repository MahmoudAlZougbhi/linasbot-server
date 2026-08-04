import CmSectionShell from "./CmSectionShell";
import { useCmSectionDraft } from "./useCmSectionDraft";

const FIELD_CLASS = "w-full rounded-xl border border-slate-200 px-3 py-2 text-sm";

/**
 * @param {unknown} value
 * @returns {string}
 */
const listToText = (value) => (Array.isArray(value) ? value.map(String).join("\n") : "");

/**
 * @param {string} text
 * @returns {string[]}
 */
const textToList = (text) =>
  text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

const CmStylePage = () => {
  const draft = useCmSectionDraft("style");
  const p = draft.payload;

  /**
   * @param {string} key
   * @param {unknown} value
   */
  const setField = (key, value) => draft.setPayload({ ...p, [key]: value });

  return (
    <CmSectionShell
      title="Style & Tone"
      description="How the AI should sound: tone, formality, length, emoji use, and writing notes."
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
        <div className="grid sm:grid-cols-2 gap-3">
          <label className="block space-y-1">
            <span className="text-sm font-medium">Tone</span>
            <input className={FIELD_CLASS} value={String(p.tone || "")} onChange={(e) => setField("tone", e.target.value)} />
          </label>
          <label className="block space-y-1">
            <span className="text-sm font-medium">Formality</span>
            <input
              className={FIELD_CLASS}
              value={String(p.formality || "")}
              onChange={(e) => setField("formality", e.target.value)}
            />
          </label>
          <label className="block space-y-1">
            <span className="text-sm font-medium">Response length</span>
            <input
              className={FIELD_CLASS}
              value={String(p.response_length || "")}
              onChange={(e) => setField("response_length", e.target.value)}
            />
          </label>
          <label className="block space-y-1">
            <span className="text-sm font-medium">Emoji level</span>
            <input
              className={FIELD_CLASS}
              value={String(p.emoji_level || "")}
              onChange={(e) => setField("emoji_level", e.target.value)}
            />
          </label>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={Boolean(p.one_question_at_a_time)}
            onChange={(e) => setField("one_question_at_a_time", e.target.checked)}
          />
          Ask one question at a time
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={Boolean(p.use_customer_name)}
            onChange={(e) => setField("use_customer_name", e.target.checked)}
          />
          Use customer name when known
        </label>
        <label className="block space-y-1">
          <span className="text-sm font-medium">Preferred terms (one per line)</span>
          <textarea
            className={FIELD_CLASS}
            rows={3}
            value={listToText(p.preferred_terms)}
            onChange={(e) => setField("preferred_terms", textToList(e.target.value))}
          />
        </label>
        <label className="block space-y-1">
          <span className="text-sm font-medium">Example replies (one per line)</span>
          <textarea
            className={FIELD_CLASS}
            rows={3}
            value={listToText(p.example_replies)}
            onChange={(e) => setField("example_replies", textToList(e.target.value))}
          />
        </label>
        <label className="block space-y-1">
          <span className="text-sm font-medium">Do (one per line)</span>
          <textarea
            className={FIELD_CLASS}
            rows={3}
            value={listToText(p.do_list)}
            onChange={(e) => setField("do_list", textToList(e.target.value))}
          />
        </label>
        <label className="block space-y-1">
          <span className="text-sm font-medium">Don&apos;t (one per line)</span>
          <textarea
            className={FIELD_CLASS}
            rows={3}
            value={listToText(p.dont_list)}
            onChange={(e) => setField("dont_list", textToList(e.target.value))}
          />
        </label>
        <label className="block space-y-1">
          <span className="text-sm font-medium">Style notes</span>
          <textarea
            className={FIELD_CLASS}
            rows={8}
            value={String(p.style_body || "")}
            onChange={(e) => setField("style_body", e.target.value)}
          />
        </label>
        <label className="block space-y-1">
          <span className="text-sm font-medium">Notes</span>
          <textarea
            className={FIELD_CLASS}
            rows={2}
            value={String(p.notes || "")}
            onChange={(e) => setField("notes", e.target.value)}
          />
        </label>
      </div>
    </CmSectionShell>
  );
};

export default CmStylePage;
