import { useState } from "react";
import { PlusIcon } from "@heroicons/react/24/outline";
import { CmArticleAttachments } from "./CmArticleAttachments";
import { CmBranchHoursFields, emptyHours, emptyWeeklySchedule } from "./CmBranchHoursFields";
import CmSectionShell from "./CmSectionShell";
import { asRecord, asRecordList, emptyLabels, newId, primaryLabel } from "./cmDraftHelpers";
import { useCmSectionDraft } from "./useCmSectionDraft";

const FIELD_CLASS = "w-full rounded-xl border border-slate-200 px-3 py-2 text-sm";

const CmBranchesPage = () => {
  const draft = useCmSectionDraft("branches");
  const items = asRecordList(draft.payload.items);
  const [selectedId, setSelectedId] = useState(/** @type {string | null} */ (null));
  const [query, setQuery] = useState("");
  const [linkUrl, setLinkUrl] = useState("");
  const [linkTitle, setLinkTitle] = useState("");
  const selected = items.find((item) => String(item.id) === selectedId) || items[0] || null;
  const visible = items.filter((item) => {
    const q = query.trim().toLowerCase();
    if (!q) return true;
    const name = primaryLabel(item.labels).toLowerCase();
    const address = String(item.address || "").toLowerCase();
    return name.includes(q) || address.includes(q);
  });

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
        maps_url: "",
        hours: emptyHours(),
        weekly_schedule: emptyWeeklySchedule(),
        available: true,
        notes: null,
        attachments: [],
      },
      ...items,
    ]);
    setSelectedId(id);
  };

  /**
   * @param {string} id
   * @param {Record<string, unknown>} data
   */
  const patch = (id, data) => setItems(items.map((item) => (String(item.id) === id ? { ...item, ...data } : item)));

  const attachments = Array.isArray(selected?.attachments) ? selected.attachments : [];

  return (
    <CmSectionShell
      title="Locations & hours"
      description="Manage every branch in one place. Each branch keeps its own details, hours, and media & files."
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
      <div className="mb-3 flex flex-wrap gap-2">
        <button type="button" onClick={add} className="inline-flex items-center gap-2 rounded-lg bg-teal-800 px-3 py-2 text-sm text-white">
          <PlusIcon className="w-4 h-4" /> Add branch
        </button>
        <input
          className={`${FIELD_CLASS} max-w-sm`}
          placeholder="Search branches"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>
      <div className="grid lg:grid-cols-5 gap-4">
        <ul className="lg:col-span-2 space-y-2">
          {visible.map((item) => (
            <li key={String(item.id)}>
              <button
                type="button"
                onClick={() => setSelectedId(String(item.id))}
                className={`w-full text-left rounded-xl border px-3 py-3 ${
                  selected && String(selected.id) === String(item.id) ? "border-teal-800 bg-teal-50" : "border-slate-200 bg-white"
                }`}
              >
                <div className="font-medium text-sm">{primaryLabel(item.labels) || String(item.id)}</div>
                <div className="text-xs text-slate-500 mt-1 truncate">{String(item.address || "No address")}</div>
              </button>
            </li>
          ))}
        </ul>
        {selected ? (
          <div className="lg:col-span-3 rounded-2xl border border-slate-200 bg-white p-4 space-y-3">
            <label className="block space-y-1">
              <span className="text-sm font-medium">Branch name</span>
              <input
                className={FIELD_CLASS}
                value={String(asRecord(selected.labels).en || "")}
                onChange={(e) =>
                  patch(String(selected.id), {
                    labels: { ...emptyLabels(), ...asRecord(selected.labels), en: e.target.value },
                  })
                }
              />
            </label>
            <label className="block space-y-1">
              <span className="text-sm font-medium">Address</span>
              <textarea
                className={FIELD_CLASS}
                rows={2}
                value={String(selected.address || "")}
                onChange={(e) => patch(String(selected.id), { address: e.target.value })}
              />
            </label>
            <label className="block space-y-1">
              <span className="text-sm font-medium">Map link</span>
              <input
                className={FIELD_CLASS}
                value={String(selected.maps_url || "")}
                onChange={(e) => patch(String(selected.id), { maps_url: e.target.value })}
                placeholder="https://maps.google.com/…"
              />
            </label>
            <label className="block space-y-1">
              <span className="text-sm font-medium">Branch note</span>
              <textarea
                className={FIELD_CLASS}
                rows={3}
                value={String(selected.notes || "")}
                onChange={(e) => patch(String(selected.id), { notes: e.target.value })}
              />
            </label>
            <div className="space-y-1">
              <span className="text-sm font-medium">Weekly hours</span>
              <CmBranchHoursFields
                schedule={asRecord(selected.weekly_schedule)}
                onChange={(weekly_schedule) => patch(String(selected.id), { weekly_schedule })}
              />
            </div>
            <CmArticleAttachments
              attachments={attachments}
              onChange={(next) => patch(String(selected.id), { attachments: next })}
            />
            <div className="flex gap-2">
              <input
                className={FIELD_CLASS}
                placeholder="Link title"
                value={linkTitle}
                onChange={(e) => setLinkTitle(e.target.value)}
              />
              <input
                className={FIELD_CLASS}
                placeholder="https://…"
                value={linkUrl}
                onChange={(e) => setLinkUrl(e.target.value)}
              />
              <button
                type="button"
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm shrink-0"
                onClick={() => {
                  const url = linkUrl.trim();
                  if (!url) return;
                  patch(String(selected.id), {
                    attachments: [
                      ...attachments,
                      {
                        id: newId("link"),
                        kind: "link",
                        filename: linkTitle.trim() || url,
                        url,
                        caption: "",
                        mime: "",
                        size: 0,
                      },
                    ],
                  });
                  setLinkUrl("");
                  setLinkTitle("");
                }}
              >
                Add link
              </button>
            </div>
            <button
              type="button"
              className="text-red-600 text-sm"
              onClick={() => {
                setItems(items.filter((item) => String(item.id) !== String(selected.id)));
                setSelectedId(null);
              }}
            >
              Delete branch
            </button>
          </div>
        ) : (
          <p className="lg:col-span-3 text-sm text-slate-500">No branches yet.</p>
        )}
      </div>
    </CmSectionShell>
  );
};

export default CmBranchesPage;
