import { useState } from "react";
import { PlusIcon } from "@heroicons/react/24/outline";
import CmSectionShell from "./CmSectionShell";
import { asRecordList, newId } from "./cmDraftHelpers";
import { useCmSectionDraft } from "./useCmSectionDraft";

const FIELD_CLASS = "w-full rounded-xl border border-slate-200 px-3 py-2 text-sm";

const ACTIONS = [
  { value: "reply_comment", label: "Reply on the comment (public)" },
  { value: "reply_dm", label: "Reply via private DM" },
  { value: "ignore", label: "Do not reply" },
];

const CmCommentsPage = () => {
  const draft = useCmSectionDraft("comments");
  const rules = asRecordList(draft.payload.rules);
  const [selectedId, setSelectedId] = useState(/** @type {string | null} */ (null));
  const selected = rules.find((item) => String(item.id) === selectedId) || rules[0] || null;

  /**
   * @param {Array<Record<string, unknown>>} next
   */
  const setRules = (next) => draft.setPayload({ ...draft.payload, rules: next });

  const add = () => {
    const id = newId("crule");
    setRules([
      {
        id,
        enabled: true,
        name: "New rule",
        match_mode: "any_keyword",
        keywords: [],
        pattern: "",
        post_id: "",
        channel: "any",
        action: "reply_comment",
        reply_template: "",
        notes: null,
      },
      ...rules,
    ]);
    setSelectedId(id);
  };

  /**
   * @param {string} id
   * @param {Record<string, unknown>} patch
   */
  const patch = (id, patchData) =>
    setRules(rules.map((item) => (String(item.id) === id ? { ...item, ...patchData } : item)));

  return (
    <CmSectionShell
      title="Comments Policy"
      description="Control how the AI handles public comments: match keywords → reply publicly, send a private DM, or ignore. Turn on comment replies in Actions + per-asset settings; Meta Advanced Access is still required for live replies."
      countLabel={`${rules.length} rules`}
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
      <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950 mb-3">
        <p>
          <strong>reply_dm</strong> uses Meta private reply (comment → DM). It does <em>not</em> fall back to a
          public comment. Live comment replies still need Meta Advanced Access + comment scopes.
        </p>
        <p className="mt-1 text-xs text-amber-900/80">
          Optional <code>post_id</code>: paste a Meta post/media id to scope a rule. Full post picker is a later
          follow-up.
        </p>
      </div>

      <div className="grid sm:grid-cols-2 gap-3 mb-4">
        <label className="block space-y-1">
          <span className="text-sm font-medium">Default when no rule matches</span>
          <select
            className={FIELD_CLASS}
            value={String(draft.payload.default_action || "reply_comment")}
            onChange={(e) => draft.setPayload({ ...draft.payload, default_action: e.target.value })}
          >
            <option value="reply_comment">AI replies on the comment</option>
            <option value="ignore">Ignore (no reply)</option>
          </select>
        </label>
        <label className="block space-y-1">
          <span className="text-sm font-medium">Policy text (for AI when no fixed template)</span>
          <textarea
            className={FIELD_CLASS}
            rows={2}
            value={String(draft.payload.policy_text || "")}
            onChange={(e) => draft.setPayload({ ...draft.payload, policy_text: e.target.value })}
            placeholder="e.g. Keep public replies short; ask for booking details in DM."
          />
        </label>
      </div>

      <div className="mb-3">
        <button
          type="button"
          onClick={add}
          className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-3 py-2 text-sm text-white"
        >
          <PlusIcon className="w-4 h-4" /> Add rule
        </button>
      </div>

      <div className="grid lg:grid-cols-5 gap-4">
        <ul className="lg:col-span-2 space-y-2">
          {rules.map((item) => (
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
                <div className="font-medium text-sm">{String(item.name || item.id)}</div>
                <div className="text-xs text-slate-500 mt-1">
                  {item.enabled === false ? "Off · " : ""}
                  {String(item.action || "reply_comment")}
                </div>
              </button>
            </li>
          ))}
          {rules.length === 0 ? <li className="text-sm text-slate-500">No rules yet — AI uses default action.</li> : null}
        </ul>

        {selected ? (
          <div className="lg:col-span-3 rounded-2xl border border-slate-200 bg-white p-4 space-y-3">
            <label className="block space-y-1">
              <span className="text-sm font-medium">Name</span>
              <input
                className={FIELD_CLASS}
                value={String(selected.name || "")}
                onChange={(e) => patch(String(selected.id), { name: e.target.value })}
              />
            </label>
            <div className="grid sm:grid-cols-2 gap-2">
              <label className="block space-y-1">
                <span className="text-sm font-medium">Match mode</span>
                <select
                  className={FIELD_CLASS}
                  value={String(selected.match_mode || "any_keyword")}
                  onChange={(e) => patch(String(selected.id), { match_mode: e.target.value })}
                >
                  <option value="any_keyword">Any keyword</option>
                  <option value="contains">Contains (any of keywords)</option>
                  <option value="regex">Regex</option>
                </select>
              </label>
              <label className="block space-y-1">
                <span className="text-sm font-medium">Channel</span>
                <select
                  className={FIELD_CLASS}
                  value={String(selected.channel || "any")}
                  onChange={(e) => patch(String(selected.id), { channel: e.target.value })}
                >
                  <option value="any">Any</option>
                  <option value="facebook">Facebook</option>
                  <option value="instagram">Instagram</option>
                </select>
              </label>
            </div>
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
                placeholder="price, سعر, book"
              />
            </label>
            {String(selected.match_mode) === "regex" ? (
              <label className="block space-y-1">
                <span className="text-sm font-medium">Regex pattern</span>
                <input
                  className={FIELD_CLASS}
                  value={String(selected.pattern || "")}
                  onChange={(e) => patch(String(selected.id), { pattern: e.target.value })}
                />
              </label>
            ) : null}
            <label className="block space-y-1">
              <span className="text-sm font-medium">Optional Meta post / media id</span>
              <input
                className={FIELD_CLASS}
                value={String(selected.post_id || "")}
                onChange={(e) => patch(String(selected.id), { post_id: e.target.value })}
                placeholder="Leave empty = all posts"
              />
            </label>
            <label className="block space-y-1">
              <span className="text-sm font-medium">Action</span>
              <select
                className={FIELD_CLASS}
                value={String(selected.action || "reply_comment")}
                onChange={(e) => patch(String(selected.id), { action: e.target.value })}
              >
                {ACTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="block space-y-1">
              <span className="text-sm font-medium">
                {String(selected.action) === "reply_dm" ? "DM message (required)" : "Fixed public reply (optional)"}
              </span>
              <textarea
                className={FIELD_CLASS}
                rows={3}
                value={String(selected.reply_template || "")}
                onChange={(e) => patch(String(selected.id), { reply_template: e.target.value })}
                placeholder={
                  String(selected.action) === "reply_dm"
                    ? "Message sent privately to the commenter"
                    : "Leave empty to let the AI write the public reply"
                }
              />
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={selected.enabled !== false}
                onChange={(e) => patch(String(selected.id), { enabled: e.target.checked })}
              />
              Enabled
            </label>
            <button
              type="button"
              className="text-sm text-rose-700 hover:underline"
              onClick={() => setRules(rules.filter((r) => String(r.id) !== String(selected.id)))}
            >
              Delete rule
            </button>
          </div>
        ) : null}
      </div>
    </CmSectionShell>
  );
};

export default CmCommentsPage;
