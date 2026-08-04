import { useState } from "react";
import { PlusIcon } from "@heroicons/react/24/outline";
import { Link } from "react-router-dom";
import CmSectionShell from "./CmSectionShell";
import { asRecord, asRecordList, emptyLabels, newId, primaryLabel } from "./cmDraftHelpers";
import { useCmSectionDraft } from "./useCmSectionDraft";

const FIELD_CLASS = "w-full rounded-xl border border-slate-200 px-3 py-2 text-sm";

const CmRestrictedPage = () => {
  const draft = useCmSectionDraft("restricted");
  const topics = asRecordList(draft.payload.topics);
  const [selectedId, setSelectedId] = useState(/** @type {string | null} */ (null));
  const selected = topics.find((item) => String(item.id) === selectedId) || topics[0] || null;

  /**
   * @param {Array<Record<string, unknown>>} next
   */
  const setTopics = (next) => draft.setPayload({ ...draft.payload, topics: next });

  const add = () => {
    const id = newId("topic");
    setTopics([
      {
        id,
        labels: emptyLabels(),
        keywords: [],
        active: true,
        refuse_template: "",
        notes: null,
      },
      ...topics,
    ]);
    setSelectedId(id);
  };

  /**
   * @param {string} id
   * @param {Record<string, unknown>} patch
   */
  const patch = (id, patch) => setTopics(topics.map((item) => (String(item.id) === id ? { ...item, ...patch } : item)));

  return (
    <CmSectionShell
      title="Restricted / Unsupported"
      description="Topics that must never be offered, priced, or WhatsApp-routed. Restricted knowledge/FAQ content remains visible under Knowledge/FAQ with status Restricted, but is not used by AI."
      countLabel={`${topics.length} restricted topics`}
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
      <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-900 mb-3">
        Tattoo removal, CO₂, pigmentation, and facial/skin cleaning stay blocked unless you deliberately deactivate a topic.
        View archived restricted articles in{" "}
        <Link className="underline" to="/content-managers/knowledge">
          Knowledge
        </Link>{" "}
        (filter: Restricted).
      </div>
      <div className="mb-3">
        <button type="button" onClick={add} className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-3 py-2 text-sm text-white">
          <PlusIcon className="w-4 h-4" /> Add topic
        </button>
      </div>
      <div className="grid lg:grid-cols-5 gap-4">
        <ul className="lg:col-span-2 space-y-2">
          {topics.map((item) => (
            <li key={String(item.id)}>
              <button
                type="button"
                onClick={() => setSelectedId(String(item.id))}
                className={`w-full text-left rounded-xl border px-3 py-3 ${
                  selected && String(selected.id) === String(item.id) ? "border-slate-900 bg-slate-50" : "border-slate-200 bg-white"
                }`}
              >
                <div className="font-medium text-sm">{primaryLabel(item.labels) || String(item.id)}</div>
                <div className="text-xs text-slate-500 mt-1">{item.active === false ? "Inactive" : "Active block"}</div>
              </button>
            </li>
          ))}
        </ul>
        {selected ? (
          <div className="lg:col-span-3 rounded-2xl border border-slate-200 bg-white p-4 space-y-3">
            {["en", "ar", "fr"].map((lang) => (
              <label key={lang} className="block space-y-1">
                <span className="text-sm font-medium">Label ({lang})</span>
                <input
                  className={FIELD_CLASS}
                  value={String(asRecord(selected.labels)[lang] || "")}
                  onChange={(e) =>
                    patch(String(selected.id), {
                      labels: { ...emptyLabels(), ...asRecord(selected.labels), [lang]: e.target.value },
                    })
                  }
                />
              </label>
            ))}
            <label className="block space-y-1">
              <span className="text-sm font-medium">Keywords (comma-separated)</span>
              <input
                className={FIELD_CLASS}
                value={Array.isArray(selected.keywords) ? selected.keywords.map(String).join(", ") : ""}
                onChange={(e) =>
                  patch(String(selected.id), {
                    keywords: e.target.value
                      .split(",")
                      .map((x) => x.trim())
                      .filter(Boolean),
                  })
                }
              />
            </label>
            <label className="block space-y-1">
              <span className="text-sm font-medium">Refuse template</span>
              <textarea
                className={FIELD_CLASS}
                rows={3}
                value={String(selected.refuse_template || "")}
                onChange={(e) => patch(String(selected.id), { refuse_template: e.target.value })}
              />
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={selected.active !== false}
                onChange={(e) => patch(String(selected.id), { active: e.target.checked })}
              />
              Active (blocked from AI / handoff)
            </label>
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
        ) : null}
      </div>
    </CmSectionShell>
  );
};

export default CmRestrictedPage;
