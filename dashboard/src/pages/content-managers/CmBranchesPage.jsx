import { useState } from "react";
import { PlusIcon } from "@heroicons/react/24/outline";
import CmSectionShell from "./CmSectionShell";
import { asRecord, asRecordList, emptyLabels, newId, primaryLabel } from "./cmDraftHelpers";
import { useCmSectionDraft } from "./useCmSectionDraft";

const FIELD_CLASS = "w-full rounded-xl border border-slate-200 px-3 py-2 text-sm";
const DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"];

const emptyHours = () => ({
  monday: "",
  tuesday: "",
  wednesday: "",
  thursday: "",
  friday: "",
  saturday: "",
  sunday: "",
  summary: "",
});

const CmBranchesPage = () => {
  const draft = useCmSectionDraft("branches");
  const items = asRecordList(draft.payload.items);
  const [selectedId, setSelectedId] = useState(/** @type {string | null} */ (null));
  const selected = items.find((item) => String(item.id) === selectedId) || items[0] || null;

  /**
   * @param {Array<Record<string, unknown>>} next
   */
  const setItems = (next) => draft.setPayload({ ...draft.payload, items: next });

  const add = () => {
    const id = newId("branch");
    setItems([
      {
        id,
        labels: emptyLabels(),
        address: "",
        hours: emptyHours(),
        available: true,
        notes: null,
      },
      ...items,
    ]);
    setSelectedId(id);
  };

  /**
   * @param {string} id
   * @param {Record<string, unknown>} patch
   */
  const patch = (id, patch) => setItems(items.map((item) => (String(item.id) === id ? { ...item, ...patch } : item)));

  const hours = asRecord(selected?.hours);

  return (
    <CmSectionShell
      title="Branches & Hours"
      description="Locations, addresses, and weekly opening hours recovered from your existing data. Blank fields mean no proven value was found — nothing is invented."
      countLabel={`${items.length} branches`}
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
      <div className="mb-4 rounded-2xl border border-slate-200 bg-white p-4 space-y-2">
        <label className="block space-y-1">
          <span className="text-sm font-medium text-slate-800">Location policy</span>
          <p className="text-xs text-slate-500">
            Branch routing rules and location guidance recovered from Knowledge. Blank means nothing proven was found — nothing is invented.
          </p>
          <textarea
            className={FIELD_CLASS}
            rows={6}
            value={String(draft.payload.policy_text || "")}
            onChange={(e) => draft.setPayload({ ...draft.payload, policy_text: e.target.value })}
          />
        </label>
      </div>
      <div className="mb-3">
        <button type="button" onClick={add} className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-3 py-2 text-sm text-white">
          <PlusIcon className="w-4 h-4" /> Add branch
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
                <div className="font-medium text-sm">{primaryLabel(item.labels) || String(item.id)}</div>
                <div className="text-xs text-slate-500 mt-1 truncate">{String(item.address || "No address on file")}</div>
              </button>
            </li>
          ))}
        </ul>
        {selected ? (
          <div className="lg:col-span-3 rounded-2xl border border-slate-200 bg-white p-4 space-y-3">
            {["en", "ar", "fr"].map((lang) => (
              <label key={lang} className="block space-y-1">
                <span className="text-sm font-medium">Branch name ({lang})</span>
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
              <span className="text-sm font-medium">Address</span>
              <textarea
                className={FIELD_CLASS}
                rows={2}
                value={String(selected.address || "")}
                onChange={(e) => patch(String(selected.id), { address: e.target.value })}
              />
            </label>
            <div className="grid sm:grid-cols-2 gap-2">
              {DAYS.map((day) => (
                <label key={day} className="block space-y-1">
                  <span className="text-sm font-medium capitalize">{day}</span>
                  <input
                    className={FIELD_CLASS}
                    value={String(hours[day] || "")}
                    onChange={(e) =>
                      patch(String(selected.id), {
                        hours: { ...emptyHours(), ...hours, [day]: e.target.value },
                      })
                    }
                    placeholder="e.g. 10:00-19:00 or Closed"
                  />
                </label>
              ))}
            </div>
            <label className="block space-y-1">
              <span className="text-sm font-medium">Hours summary</span>
              <input
                className={FIELD_CLASS}
                value={String(hours.summary || "")}
                onChange={(e) =>
                  patch(String(selected.id), {
                    hours: { ...emptyHours(), ...hours, summary: e.target.value },
                  })
                }
              />
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={selected.available !== false}
                onChange={(e) => patch(String(selected.id), { available: e.target.checked })}
              />
              Branch available
            </label>
            <label className="block space-y-1">
              <span className="text-sm font-medium">Branch notes</span>
              <textarea
                className={FIELD_CLASS}
                rows={3}
                value={String(selected.notes || "")}
                onChange={(e) => patch(String(selected.id), { notes: e.target.value })}
              />
            </label>
          </div>
        ) : (
          <p className="lg:col-span-3 text-sm text-slate-500">No branches yet.</p>
        )}
      </div>
    </CmSectionShell>
  );
};

export default CmBranchesPage;
