import { useState } from "react";
import { PlusIcon } from "@heroicons/react/24/outline";
import CmSectionShell from "./CmSectionShell";
import { asRecordList, newId } from "./cmDraftHelpers";
import { useCmSectionDraft } from "./useCmSectionDraft";

const FIELD_CLASS = "w-full rounded-xl border border-slate-200 px-3 py-2 text-sm";

const CmDynamicMessagesPage = () => {
  const draft = useCmSectionDraft("dynamic_messages");
  const items = asRecordList(draft.payload.items);
  const [selectedId, setSelectedId] = useState(/** @type {string | null} */ (null));
  const [lang, setLang] = useState("ar");
  const selected = items.find((item) => String(item.id) === selectedId) || items[0] || null;

  /**
   * @param {Array<Record<string, unknown>>} next
   */
  const setItems = (next) => draft.setPayload({ ...draft.payload, items: next });

  const add = () => {
    const id = newId("msg");
    setItems([{ id, name: "New message", ar: "", en: "", fr: "", notes: null }, ...items]);
    setSelectedId(id);
  };

  /**
   * @param {string} id
   * @param {Record<string, unknown>} patch
   */
  const patch = (id, patch) => setItems(items.map((item) => (String(item.id) === id ? { ...item, ...patch } : item)));

  return (
    <CmSectionShell
      title="Dynamic Messages"
      description="Greeting and system message templates by language, with live preview."
      countLabel={`${items.length} templates`}
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
      <div className="mb-3">
        <button type="button" onClick={add} className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-3 py-2 text-sm text-white">
          <PlusIcon className="w-4 h-4" /> Add template
        </button>
      </div>
      <div className="grid lg:grid-cols-5 gap-4">
        <ul className="lg:col-span-2 space-y-2">
          {items.map((item) => (
            <li key={String(item.id)}>
              <button
                type="button"
                onClick={() => setSelectedId(String(item.id))}
                className={`w-full text-left rounded-xl border px-3 py-3 ${
                  selected && String(selected.id) === String(item.id) ? "border-slate-900 bg-slate-50" : "border-slate-200 bg-white"
                }`}
              >
                <div className="font-medium text-sm">{String(item.name || item.id)}</div>
              </button>
            </li>
          ))}
        </ul>
        {selected ? (
          <div className="lg:col-span-3 rounded-2xl border border-slate-200 bg-white p-4 space-y-3">
            <label className="block space-y-1">
              <span className="text-sm font-medium">Template name</span>
              <input
                className={FIELD_CLASS}
                value={String(selected.name || "")}
                onChange={(e) => patch(String(selected.id), { name: e.target.value })}
              />
            </label>
            <div className="flex gap-2">
              {["ar", "en", "fr"].map((code) => (
                <button
                  key={code}
                  type="button"
                  onClick={() => setLang(code)}
                  className={`rounded-lg px-3 py-1.5 text-sm border ${
                    lang === code ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200"
                  }`}
                >
                  {code.toUpperCase()}
                </button>
              ))}
            </div>
            <label className="block space-y-1">
              <span className="text-sm font-medium">Message ({lang})</span>
              <textarea
                className={FIELD_CLASS}
                rows={5}
                value={String(selected[lang] || "")}
                onChange={(e) => patch(String(selected.id), { [lang]: e.target.value })}
              />
            </label>
            <div className="rounded-xl bg-slate-50 border border-slate-200 p-3 text-sm whitespace-pre-wrap">
              <div className="text-xs uppercase tracking-wide text-slate-500 mb-1">Preview</div>
              {String(selected[lang] || "—")}
            </div>
            <label className="block space-y-1">
              <span className="text-sm font-medium">Notes</span>
              <textarea
                className={FIELD_CLASS}
                rows={2}
                value={String(selected.notes || "")}
                onChange={(e) => patch(String(selected.id), { notes: e.target.value })}
              />
            </label>
          </div>
        ) : (
          <p className="lg:col-span-3 text-sm text-slate-500">No templates yet.</p>
        )}
      </div>
    </CmSectionShell>
  );
};

export default CmDynamicMessagesPage;
