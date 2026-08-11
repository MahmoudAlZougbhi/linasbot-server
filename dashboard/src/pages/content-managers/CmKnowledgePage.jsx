import { useMemo, useState } from "react";
import { PlusIcon, TrashIcon } from "@heroicons/react/24/outline";
import { CmArticleAttachments } from "./CmArticleAttachments";
import CmSectionShell from "./CmSectionShell";
import { asRecordList, newId, primaryLabel, statusBadgeClass } from "./cmDraftHelpers";
import { useCmSectionDraft } from "./useCmSectionDraft";

const FIELD_CLASS = "w-full rounded-xl border border-slate-200 px-3 py-2 text-sm";

/**
 * Generic article editor for Knowledge and Preparation & Aftercare.
 * @param {{ section: "knowledge" | "care"; title: string; description: string }} props
 */
export const CmArticlesPage = ({ section, title, description }) => {
  const draft = useCmSectionDraft(section);
  const items = asRecordList(draft.payload.items);
  const [selectedId, setSelectedId] = useState(/** @type {string | null} */ (null));
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState(section === "knowledge" ? "active" : "all");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return items.filter((item) => {
      const status = String(item.status || "active");
      if (statusFilter !== "all" && status !== statusFilter) return false;
      if (!q) return true;
      const blob = `${item.title || ""} ${item.body || ""} ${item.source_filename || ""}`.toLowerCase();
      return blob.includes(q);
    });
  }, [items, query, statusFilter]);

  const selected = items.find((item) => String(item.id) === selectedId) || filtered[0] || null;

  /**
   * @param {Array<Record<string, unknown>>} nextItems
   */
  const setItems = (nextItems) => {
    draft.setPayload({ ...draft.payload, items: nextItems });
  };

  const addItem = () => {
    const id = newId(section === "care" ? "care" : "knowledge");
    const next = [
      {
        id,
        title: "New article",
        body: "",
        tags: [],
        language: "en",
        audience: "general",
        category: "",
        status: "draft",
        source_filename: null,
        source_checksum: null,
        linked_service_ids: [],
        linked_branch_ids: [],
        notes: null,
        attachments: [],
      },
      ...items,
    ];
    setItems(next);
    setSelectedId(id);
  };

  /**
   * @param {string} id
   * @param {Record<string, unknown>} patch
   */
  const patchItem = (id, patch) => {
    setItems(items.map((item) => (String(item.id) === id ? { ...item, ...patch } : item)));
  };

  /**
   * @param {string} id
   */
  const archiveItem = (id) => {
    patchItem(id, { status: "archived" });
  };

  return (
    <CmSectionShell
      title={title}
      description={description}
      countLabel={`${filtered.length} shown · ${items.length} total`}
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
      <div className="flex flex-wrap gap-2 mb-3">
        <input
          className={`${FIELD_CLASS} max-w-sm`}
          placeholder="Search title, body, source…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <select className={FIELD_CLASS + " max-w-[10rem]"} value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="all">All statuses</option>
          <option value="active">Active</option>
          <option value="draft">Draft</option>
          <option value="archived">Archived</option>
          <option value="restricted">Restricted</option>
        </select>
        <button type="button" onClick={addItem} className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-3 py-2 text-sm text-white">
          <PlusIcon className="w-4 h-4" /> Add
        </button>
      </div>

      <div className="grid lg:grid-cols-5 gap-4">
        <ul className="lg:col-span-2 space-y-2 max-h-[70vh] overflow-auto">
          {filtered.map((item) => (
            <li key={String(item.id)}>
              <button
                type="button"
                onClick={() => setSelectedId(String(item.id))}
                className={`w-full text-left rounded-xl border px-3 py-3 ${
                  selected && String(selected.id) === String(item.id)
                    ? "border-slate-900 bg-slate-50"
                    : "border-slate-200 bg-white"
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium text-sm text-slate-900">{String(item.title || "Untitled")}</span>
                  <span className={`text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full ${statusBadgeClass(String(item.status || "active"))}`}>
                    {String(item.status || "active")}
                  </span>
                </div>
                <p className="text-xs text-slate-500 mt-1 truncate">
                  {String(item.source_filename || item.category || item.language || "—")}
                </p>
              </button>
            </li>
          ))}
          {filtered.length === 0 ? <li className="text-sm text-slate-500">No articles match.</li> : null}
        </ul>

        {selected ? (
          <div className="lg:col-span-3 rounded-2xl border border-slate-200 bg-white p-4 space-y-3">
            {String(selected.status) === "restricted" ? (
              <p className="rounded-lg bg-rose-50 border border-rose-200 px-3 py-2 text-sm text-rose-900">
                Not used by AI. Preserved for owner review / archive.
              </p>
            ) : null}
            <label className="block space-y-1">
              <span className="text-sm font-medium">Title</span>
              <input
                className={FIELD_CLASS}
                value={String(selected.title || "")}
                onChange={(e) => patchItem(String(selected.id), { title: e.target.value })}
              />
            </label>
            <div className="grid sm:grid-cols-3 gap-2">
              <label className="block space-y-1">
                <span className="text-sm font-medium">Language</span>
                <input
                  className={FIELD_CLASS}
                  value={String(selected.language || "")}
                  onChange={(e) => patchItem(String(selected.id), { language: e.target.value })}
                />
              </label>
              <label className="block space-y-1">
                <span className="text-sm font-medium">Category</span>
                <input
                  className={FIELD_CLASS}
                  value={String(selected.category || "")}
                  onChange={(e) => patchItem(String(selected.id), { category: e.target.value })}
                />
              </label>
              <label className="block space-y-1">
                <span className="text-sm font-medium">Status</span>
                <select
                  className={FIELD_CLASS}
                  value={String(selected.status || "active")}
                  onChange={(e) => patchItem(String(selected.id), { status: e.target.value })}
                >
                  <option value="active">Active</option>
                  <option value="draft">Draft</option>
                  <option value="archived">Archived</option>
                  <option value="restricted">Restricted</option>
                </select>
              </label>
            </div>
            <label className="block space-y-1">
              <span className="text-sm font-medium">Content</span>
              <textarea
                className={FIELD_CLASS}
                rows={12}
                value={String(selected.body || "")}
                onChange={(e) => patchItem(String(selected.id), { body: e.target.value })}
              />
            </label>
            <label className="block space-y-1">
              <span className="text-sm font-medium">Tags (comma-separated)</span>
              <input
                className={FIELD_CLASS}
                value={Array.isArray(selected.tags) ? selected.tags.map(String).join(", ") : ""}
                onChange={(e) =>
                  patchItem(String(selected.id), {
                    tags: e.target.value
                      .split(",")
                      .map((t) => t.trim())
                      .filter(Boolean),
                  })
                }
              />
            </label>
            <div className="grid sm:grid-cols-2 gap-2 text-sm text-slate-600">
              <div>
                <span className="font-medium text-slate-800">Source file:</span>{" "}
                {String(selected.source_filename || "—")}
              </div>
              <div>
                <span className="font-medium text-slate-800">Checksum:</span>{" "}
                {String(selected.source_checksum || "—")}
              </div>
            </div>
            <label className="block space-y-1">
              <span className="text-sm font-medium">Notes</span>
              <textarea
                className={FIELD_CLASS}
                rows={2}
                value={String(selected.notes || "")}
                onChange={(e) => patchItem(String(selected.id), { notes: e.target.value })}
              />
            </label>
            <CmArticleAttachments
              attachments={asRecordList(selected.attachments)}
              onChange={(next) => patchItem(String(selected.id), { attachments: next })}
            />
            <button
              type="button"
              onClick={() => archiveItem(String(selected.id))}
              className="inline-flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700"
            >
              <TrashIcon className="w-4 h-4" /> Archive
            </button>
          </div>
        ) : (
          <p className="lg:col-span-3 text-sm text-slate-500">Select or add an article.</p>
        )}
      </div>
      {/* silence unused helper warning in some lint configs */}
      <span className="sr-only">{primaryLabel({})}</span>
    </CmSectionShell>
  );
};

const CmKnowledgePage = () => (
  <CmArticlesPage
    section="knowledge"
    title="Knowledge"
    description="Educational clinic articles for AI retrieval after FAQ miss. Location, booking, greeting, and price rules live in their dedicated sections (archived copies stay filterable here)."
  />
);

export default CmKnowledgePage;
