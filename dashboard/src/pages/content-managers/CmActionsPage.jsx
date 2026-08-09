import CmSectionShell from "./CmSectionShell";
import { useCmSectionDraft } from "./useCmSectionDraft";

const FIELD = "w-full rounded-xl border border-slate-200 px-3 py-2 text-sm";

/** @type {Record<string, string>} */
const ACTION_LABELS = {
  respond_facebook_dm: "Respond to Facebook DMs",
  respond_instagram_dm: "Respond to Instagram DMs",
  respond_facebook_comments: "Respond to Facebook comments",
  respond_instagram_comments: "Respond to Instagram comments",
  human_handoff: "Human handoff",
  photo_analysis: "Photo analysis",
};

const CmActionsPage = () => {
  const draft = useCmSectionDraft("actions");
  const items = (Array.isArray(draft.payload.items) ? draft.payload.items : []).filter(
    (item) => item?.id !== "photo_analysis",
  );

  /**
   * @param {number} index
   * @param {boolean} enabled
   */
  const setEnabled = (index, enabled) => {
    const all = Array.isArray(draft.payload.items) ? draft.payload.items : [];
    // Map filtered UI index back onto the full items array (photo_analysis may still exist in draft).
    const visibleIds = items.map((item) => item.id);
    const targetId = visibleIds[index];
    const next = all.map((item) => (item.id === targetId ? { ...item, enabled } : item));
    draft.setPayload({ ...draft.payload, items: next });
  };

  return (
    <CmSectionShell
      title="Actions / Capabilities"
      description="Choose what this AI is allowed to do. Voice processing and image analysis are managed under AI Limits."
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
      <div className="space-y-3 max-w-2xl">
        {items.map((item, index) => (
          <label key={String(item.id)} className="flex items-center justify-between rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm">
            <span>{ACTION_LABELS[String(item.id)] || String(item.id)}</span>
            <input
              type="checkbox"
              checked={Boolean(item.enabled)}
              onChange={(e) => setEnabled(index, e.target.checked)}
            />
          </label>
        ))}
        <label className="block space-y-1">
          <span className="text-sm font-medium">Notes</span>
          <textarea
            className={FIELD}
            rows={2}
            value={String(draft.payload.notes || "")}
            onChange={(e) => draft.setPayload({ ...draft.payload, notes: e.target.value })}
          />
        </label>
      </div>
    </CmSectionShell>
  );
};

export default CmActionsPage;
