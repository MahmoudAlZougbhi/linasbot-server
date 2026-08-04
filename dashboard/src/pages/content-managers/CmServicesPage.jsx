import { useMemo, useState } from "react";
import { PlusIcon } from "@heroicons/react/24/outline";
import CmSectionShell from "./CmSectionShell";
import { asRecord, asRecordList, emptyLabels, newId, primaryLabel } from "./cmDraftHelpers";
import { useCmSectionDraft } from "./useCmSectionDraft";

const FIELD_CLASS = "w-full rounded-xl border border-slate-200 px-3 py-2 text-sm";

const CmServicesPage = () => {
  const draft = useCmSectionDraft("services");
  const items = asRecordList(draft.payload.items);
  const [selectedId, setSelectedId] = useState(/** @type {string | null} */ (null));
  const selected = items.find((item) => String(item.id) === selectedId) || items[0] || null;

  const countLabel = useMemo(() => {
    const active = items.filter((item) => item.available !== false).length;
    return `${items.length} services · ${active} available`;
  }, [items]);

  /**
   * @param {Array<Record<string, unknown>>} next
   */
  const setItems = (next) => draft.setPayload({ ...draft.payload, items: next });

  const add = () => {
    const id = newId("service");
    setItems([
      {
        id,
        labels: emptyLabels(),
        available: true,
        category: "laser_hair_removal",
        aliases: [],
        audience: "general",
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

  return (
    <CmSectionShell
      title="Services"
      description="Active service catalog used by answers and booking. Add every service Linas actually offers (laser hair removal, tattoo removal, CO₂, DPL whitening, etc.). Do not invent services."
      countLabel={countLabel}
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
          <PlusIcon className="w-4 h-4" /> Add service
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
                <div className="text-xs text-slate-500 mt-1">{item.available === false ? "Archived / unavailable" : "Available"}</div>
              </button>
            </li>
          ))}
        </ul>
        {selected ? (
          <div className="lg:col-span-3 rounded-2xl border border-slate-200 bg-white p-4 space-y-3">
            {["en", "ar", "fr", "franco"].map((lang) => (
              <label key={lang} className="block space-y-1">
                <span className="text-sm font-medium">Name ({lang})</span>
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
              <span className="text-sm font-medium">Aliases (comma-separated)</span>
              <input
                className={FIELD_CLASS}
                value={Array.isArray(selected.aliases) ? selected.aliases.map(String).join(", ") : ""}
                onChange={(e) =>
                  patch(String(selected.id), {
                    aliases: e.target.value
                      .split(",")
                      .map((x) => x.trim())
                      .filter(Boolean),
                  })
                }
              />
            </label>
            <div className="grid sm:grid-cols-2 gap-2">
              <label className="block space-y-1">
                <span className="text-sm font-medium">Audience</span>
                <select
                  className={FIELD_CLASS}
                  value={String(selected.audience || "general")}
                  onChange={(e) => patch(String(selected.id), { audience: e.target.value })}
                >
                  <option value="general">General</option>
                  <option value="women">Women</option>
                  <option value="men">Men</option>
                </select>
              </label>
              <label className="flex items-center gap-2 text-sm mt-6">
                <input
                  type="checkbox"
                  checked={selected.available !== false}
                  onChange={(e) => patch(String(selected.id), { available: e.target.checked })}
                />
                Available / active
              </label>
            </div>
            <label className="block space-y-1">
              <span className="text-sm font-medium">Notes</span>
              <textarea
                className={FIELD_CLASS}
                rows={3}
                value={String(selected.notes || "")}
                onChange={(e) => patch(String(selected.id), { notes: e.target.value })}
              />
            </label>
          </div>
        ) : (
          <p className="lg:col-span-3 text-sm text-slate-500">No services yet.</p>
        )}
      </div>
    </CmSectionShell>
  );
};

export default CmServicesPage;
