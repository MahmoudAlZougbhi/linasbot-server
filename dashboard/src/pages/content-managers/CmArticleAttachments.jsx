import { useRef, useState } from "react";
import toast from "react-hot-toast";
import { useApi } from "../../hooks/useApi";

const FIELD_CLASS = "w-full rounded-xl border border-slate-200 px-3 py-2 text-sm";

/**
 * Case-example attachments on a knowledge/care article (upload + caption).
 * @param {{
 *   attachments: Array<Record<string, unknown>>;
 *   onChange: (next: Array<Record<string, unknown>>) => void;
 * }} props
 */
export function CmArticleAttachments({ attachments, onChange }) {
  const { uploadCmMedia } = useApi();
  const inputRef = useRef(/** @type {HTMLInputElement | null} */ (null));
  const [uploading, setUploading] = useState(false);

  const rows = Array.isArray(attachments) ? attachments : [];

  /**
   * @param {number} index
   * @param {Record<string, unknown>} patch
   */
  const patchRow = (index, patch) => {
    onChange(rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  };

  /**
   * @param {React.ChangeEvent<HTMLInputElement>} event
   */
  const onFile = async (event) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setUploading(true);
    try {
      const res = await uploadCmMedia(file);
      if (!res?.success || !res.media_id) {
        toast.error(res?.error || "Upload failed");
        return;
      }
      onChange([
        ...rows,
        {
          id: res.media_id,
          kind: res.kind || (String(res.mime || "").startsWith("image/") ? "image" : "file"),
          caption: "",
          mime: res.mime || file.type || "",
          filename: res.filename || file.name,
          size: res.size || file.size || 0,
        },
      ]);
      toast.success("Attachment uploaded — add a caption, then Save draft");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="space-y-3 rounded-xl border border-slate-200 bg-slate-50/60 p-3">
      <div>
        <p className="text-sm font-medium text-slate-900">Case examples (images / files)</p>
        <p className="text-xs text-slate-500 mt-0.5">
          Attach visuals or documents and describe when the AI should use each one
          (e.g. “filled intake form”, “send this PDF for package A”).
        </p>
      </div>
      {rows.map((row, index) => (
        <div key={String(row.id || index)} className="rounded-lg border border-slate-200 bg-white p-3 space-y-2">
          <div className="flex items-center justify-between gap-2 text-xs text-slate-600">
            <span>
              {String(row.kind || "file")}: {String(row.filename || row.id || "attachment")}
            </span>
            <button
              type="button"
              className="text-rose-700 hover:underline"
              onClick={() => onChange(rows.filter((_, i) => i !== index))}
            >
              Remove
            </button>
          </div>
          <label className="block space-y-1">
            <span className="text-sm font-medium">When to use (caption)</span>
            <textarea
              className={FIELD_CLASS}
              rows={2}
              value={String(row.caption || "")}
              onChange={(e) => patchRow(index, { caption: e.target.value })}
              placeholder="e.g. Use when the customer asks how a filled form looks"
            />
          </label>
        </div>
      ))}
      <input
        ref={inputRef}
        type="file"
        className="hidden"
        accept="image/jpeg,image/png,image/webp,image/heic,image/heif,application/pdf,text/plain,text/markdown,application/json,.md,.txt,.pdf"
        onChange={(e) => void onFile(e)}
      />
      <button
        type="button"
        disabled={uploading}
        onClick={() => inputRef.current?.click()}
        className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 disabled:opacity-50"
      >
        {uploading ? "Uploading…" : "Attach image or file"}
      </button>
    </div>
  );
}
