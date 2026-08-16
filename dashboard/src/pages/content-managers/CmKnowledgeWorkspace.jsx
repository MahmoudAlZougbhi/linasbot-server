import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { TrashIcon } from "@heroicons/react/24/outline";
import { CmArticleAttachments } from "./CmArticleAttachments";
import CmSectionShell from "./CmSectionShell";
import { asRecordList, newId } from "./cmDraftHelpers";
import { useCmSectionDraft } from "./useCmSectionDraft";
import {
  countWords,
  formatMediaSummary,
  formatUpdatedStamp,
  isLocationsKnowledgeTitle,
  LOCATIONS_KNOWLEDGE_TITLE,
} from "./knowledgeUi";

const FIELD =
  "w-full rounded-xl border border-slate-200 px-3 py-2 text-sm text-[#0F4C4A]";
const TEAL = "#107C75";

/**
 * Knowledge list + edit matching the mobile screenshot labels, using the CM draft API.
 */
export function CmKnowledgeWorkspace() {
  const draft = useCmSectionDraft("knowledge");
  const items = asRecordList(draft.payload.items);
  const [selectedId, setSelectedId] = useState(/** @type {string | null} */ (null));
  const [query, setQuery] = useState("");

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return items.filter((item) => {
      if (String(item.status || "") === "archived") return false;
      if (isLocationsKnowledgeTitle(String(item.title || ""))) return false;
      if (!q) return true;
      const blob = `${item.title || ""} ${item.body || ""} ${item.source_filename || ""}`.toLowerCase();
      return blob.includes(q);
    });
  }, [items, query]);

  const showLocations =
    !query.trim() || LOCATIONS_KNOWLEDGE_TITLE.toLowerCase().includes(query.trim().toLowerCase());
  const selected = items.find((item) => String(item.id) === selectedId) || null;
  const count = visible.length + (showLocations ? 1 : 0);

  /**
   * @param {Array<Record<string, unknown>>} nextItems
   */
  const setItems = (nextItems) => {
    draft.setPayload({ ...draft.payload, items: nextItems });
  };

  const addItem = () => {
    const id = newId("knowledge");
    const next = [
      {
        id,
        title: "",
        body: "",
        tags: [],
        language: "",
        audience: "general",
        category: "",
        status: "active",
        source_filename: null,
        source_checksum: null,
        linked_service_ids: [],
        linked_branch_ids: [],
        notes: null,
        attachments: [],
        updated_at: new Date().toISOString(),
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
    setItems(
      items.map((item) =>
        String(item.id) === id ? { ...item, ...patch, updated_at: new Date().toISOString() } : item,
      ),
    );
  };

  const deleteSelected = async () => {
    if (!selected) return;
    if (!window.confirm("Delete this knowledge item from the draft?")) return;
    const nextPayload = {
      ...draft.payload,
      items: items.filter((item) => String(item.id) !== String(selected.id)),
    };
    const ok = await draft.save(nextPayload);
    if (ok) setSelectedId(null);
  };

  const published = String(selected?.status || "active") === "active";
  const words = countWords(String(selected?.body || ""));

  return (
    <CmSectionShell
      title="Knowledge"
      description="Teach Linas what your business knows."
      countLabel={`${count} knowledge item${count === 1 ? "" : "s"}`}
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
          className={`${FIELD} max-w-sm`}
          placeholder="Search knowledge"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <button
          type="button"
          onClick={addItem}
          className="inline-flex items-center rounded-full px-3 py-2 text-sm text-white"
          style={{ backgroundColor: TEAL }}
        >
          + Add knowledge
        </button>
      </div>

      <div className="grid lg:grid-cols-5 gap-4">
        <ul className="lg:col-span-2 space-y-2 max-h-[70vh] overflow-auto">
          {visible.map((item) => {
            const summary = formatMediaSummary(item.attachments);
            const updated = formatUpdatedStamp(
              typeof item.updated_at === "string" ? item.updated_at : null,
            );
            return (
              <li key={String(item.id)}>
                <button
                  type="button"
                  onClick={() => setSelectedId(String(item.id))}
                  className={`w-full text-left rounded-xl border px-3 py-3 ${
                    selected && String(selected.id) === String(item.id)
                      ? "border-[#107C75] bg-[#E6F3F2]"
                      : "border-slate-200 bg-white"
                  }`}
                >
                  <span className="font-semibold text-sm text-[#0F4C4A]">
                    {String(item.title || "Untitled")}
                  </span>
                  <p className="text-xs text-slate-500 mt-1">
                    {summary}
                    {updated ? ` • ${updated}` : ""}
                  </p>
                </button>
              </li>
            );
          })}
          {showLocations ? (
            <li>
              <Link
                to="/content-managers/branches"
                className="block rounded-xl border border-slate-200 bg-white px-3 py-3"
              >
                <span className="font-semibold text-sm text-[#0F4C4A]">{LOCATIONS_KNOWLEDGE_TITLE}</span>
                <p className="text-xs text-slate-500 mt-1">Text only</p>
              </Link>
            </li>
          ) : null}
          {visible.length === 0 && !showLocations ? (
            <li className="text-sm text-slate-500">No knowledge items yet.</li>
          ) : null}
        </ul>

        {selected ? (
          <div className="lg:col-span-3 rounded-2xl border border-slate-200 bg-white p-4 space-y-3">
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-xl font-bold text-[#0F4C4A]">Edit knowledge</h2>
              <button
                type="button"
                onClick={() => patchItem(String(selected.id), { status: published ? "draft" : "active" })}
                className="inline-flex items-center gap-2 rounded-full bg-[#D7EFEB] px-3 py-1 text-sm font-medium text-[#107C75]"
              >
                <span className={`h-2 w-2 rounded-full ${published ? "bg-[#107C75]" : "bg-amber-500"}`} />
                {published ? "Published" : "Draft"}
              </button>
            </div>
            <label className="block space-y-1">
              <span className="text-sm font-bold text-[#0F4C4A]">Title</span>
              <input
                className={FIELD}
                value={String(selected.title || "")}
                onChange={(e) => patchItem(String(selected.id), { title: e.target.value })}
              />
            </label>
            <label className="block space-y-1">
              <span className="text-sm font-bold text-[#0F4C4A]">Knowledge</span>
              <textarea
                className={FIELD}
                rows={8}
                value={String(selected.body || "")}
                onChange={(e) => patchItem(String(selected.id), { body: e.target.value })}
              />
            </label>
            <p className="text-xs text-slate-500 text-right">
              {words} {words === 1 ? "word" : "words"}
            </p>
            <div className="flex gap-3 rounded-xl bg-[#E6F3F2] p-3 text-sm text-[#0F4C4A]">
              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[#107C75] text-white text-xs font-bold">
                i
              </span>
              <div className="space-y-1">
                <p className="font-semibold">Recommended: Around 1,000 words per note for clearer AI answers.</p>
                <p>This is not a limit—you can write more.</p>
                <p>You can write in any language. English is recommended for the best results.</p>
              </div>
            </div>
            <CmArticleAttachments
              variant="knowledge"
              attachments={asRecordList(selected.attachments)}
              onChange={(next) => patchItem(String(selected.id), { attachments: next })}
            />
            <div className="flex gap-2 pt-2">
              <button
                type="button"
                onClick={() => void deleteSelected()}
                className="inline-flex items-center gap-2 rounded-xl border border-red-500 px-3 py-2 text-sm font-semibold text-red-600"
              >
                <TrashIcon className="w-4 h-4" /> Delete
              </button>
              <button
                type="button"
                disabled={!draft.dirty || draft.saving}
                onClick={() => void draft.save()}
                className="rounded-xl px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
                style={{ backgroundColor: TEAL }}
              >
                Save changes
              </button>
            </div>
          </div>
        ) : (
          <p className="lg:col-span-3 text-sm text-slate-500">Select or add a knowledge item.</p>
        )}
      </div>
      <p className="text-sm text-slate-500 mt-4">Linas uses published knowledge when replying.</p>
    </CmSectionShell>
  );
}
