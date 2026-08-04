import { RESPONSE_ROWS } from "./cmLanguageConstants";
import CmSectionShell from "./CmSectionShell";
import { useCmSectionDraft } from "./useCmSectionDraft";

const FIELD_CLASS = "w-full rounded-xl border border-slate-200 px-3 py-2 text-sm";
const LANGS = [
  { id: "ar", label: "Arabic" },
  { id: "en", label: "English" },
  { id: "fr", label: "French" },
  { id: "franco", label: "Franco / Arabizi" },
];

/**
 * Language policy screen — no JSON.
 */
const CmLanguagesPage = () => {
  const draft = useCmSectionDraft("languages");
  const p = draft.payload;
  const supported = Array.isArray(p.supported_languages)
    ? /** @type {string[]} */ (p.supported_languages)
    : ["ar", "en", "fr", "franco"];

  /**
   * @param {string} lang
   */
  const toggleLang = (lang) => {
    const next = supported.includes(lang) ? supported.filter((x) => x !== lang) : [...supported, lang];
    draft.setPayload({ ...p, supported_languages: next });
  };

  return (
    <CmSectionShell
      title="Languages"
      description="Which languages the AI understands, and how answers are returned. Franco questions always get Arabic-script answers."
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
        <section className="rounded-2xl border border-slate-200 bg-white p-5 space-y-3">
          <h2 className="text-sm font-semibold text-slate-900">Supported languages</h2>
          <div className="grid sm:grid-cols-2 gap-2">
            {LANGS.map((lang) => (
              <label key={lang.id} className="flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-2 text-sm">
                <input type="checkbox" checked={supported.includes(lang.id)} onChange={() => toggleLang(lang.id)} />
                {lang.label}
              </label>
            ))}
          </div>
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-5 space-y-3">
          <h2 className="text-sm font-semibold text-slate-900">Answer language map</h2>
          <ul className="space-y-2 text-sm text-slate-700">
            {RESPONSE_ROWS.map((row) => (
              <li key={row.from} className="rounded-xl bg-slate-50 px-3 py-2">
                <span className="font-medium">{row.fromLabel}</span> question →{" "}
                <span className="font-medium">{row.toLabel}</span> answer
              </li>
            ))}
          </ul>
          <p className="text-xs text-slate-500">
            This map is product policy (Franco → Arabic script). FAQ translation status is managed on the FAQ page.
          </p>
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-5 space-y-3">
          <label className="block space-y-1">
            <span className="text-sm font-medium">Default / unknown language</span>
            <select
              className={FIELD_CLASS}
              value={String(p.default_language || "ar")}
              onChange={(e) => draft.setPayload({ ...p, default_language: e.target.value })}
            >
              {LANGS.map((lang) => (
                <option key={lang.id} value={lang.id}>
                  {lang.label}
                </option>
              ))}
            </select>
          </label>
          <label className="block space-y-1">
            <span className="text-sm font-medium">Mixed-language behavior</span>
            <textarea
              className={FIELD_CLASS}
              rows={2}
              value={String(p.mixed_language_behavior || "")}
              onChange={(e) => draft.setPayload({ ...p, mixed_language_behavior: e.target.value })}
            />
          </label>
          <label className="block space-y-1">
            <span className="text-sm font-medium">Unknown-language behavior</span>
            <textarea
              className={FIELD_CLASS}
              rows={2}
              value={String(p.unknown_language_behavior || "")}
              onChange={(e) => draft.setPayload({ ...p, unknown_language_behavior: e.target.value })}
            />
          </label>
          <label className="block space-y-1">
            <span className="text-sm font-medium">Notes</span>
            <textarea
              className={FIELD_CLASS}
              rows={2}
              value={String(p.notes || "")}
              onChange={(e) => draft.setPayload({ ...p, notes: e.target.value })}
            />
          </label>
        </section>
      </div>
    </CmSectionShell>
  );
};

export default CmLanguagesPage;
