import { useRef, useState } from "react";
import toast from "react-hot-toast";
import { useApi } from "../../hooks/useApi";
import { isValidHttpUrl } from "./knowledgeUi";

const FIELD_CLASS = "w-full rounded-xl border border-slate-200 px-3 py-2 text-sm";
const TEAL_BTN =
  "rounded-xl border border-slate-200 bg-white px-3 py-4 text-sm font-medium text-[#107C75] disabled:opacity-50";

/**
 * Case-example attachments on a knowledge/care article (upload + caption).
 * @param {{
 *   attachments: Array<Record<string, unknown>>;
 *   onChange: (next: Array<Record<string, unknown>>) => void;
 *   variant?: "care" | "knowledge";
 * }} props
 */
export function CmArticleAttachments({ attachments, onChange, variant = "care" }) {
  const { uploadCmMedia } = useApi();
  const imageRef = useRef(/** @type {HTMLInputElement | null} */ (null));
  const videoRef = useRef(/** @type {HTMLInputElement | null} */ (null));
  const fileRef = useRef(/** @type {HTMLInputElement | null} */ (null));
  const careRef = useRef(/** @type {HTMLInputElement | null} */ (null));
  const [uploading, setUploading] = useState(false);
  const [linkUrl, setLinkUrl] = useState("");
  const [showLink, setShowLink] = useState(false);

  const rows = Array.isArray(attachments) ? attachments : [];
  const knowledge = variant === "knowledge";

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
      const mime = String(res.mime || file.type || "");
      const kind =
        res.kind ||
        (mime.startsWith("image/") ? "image" : mime.startsWith("video/") ? "video" : "file");
      onChange([
        ...rows,
        {
          id: res.media_id,
          kind,
          title: "",
          description: "",
          caption: "",
          mime,
          filename: res.filename || file.name,
          size: res.size || file.size || 0,
          url: "",
          duration_seconds: null,
          status: "active",
        },
      ]);
      toast.success("Attachment uploaded — add a title and short description, then Save changes");
    } finally {
      setUploading(false);
    }
  };

  const addLink = () => {
    if (!isValidHttpUrl(linkUrl)) {
      toast.error("Enter a valid http or https URL.");
      return;
    }
    const url = linkUrl.trim();
    let host = url;
    try {
      host = new URL(url).hostname;
    } catch {
      host = url;
    }
    onChange([
      ...rows,
      {
        id: `link_${Date.now().toString(36)}`,
        kind: "link",
        title: host,
        description: "",
        caption: "",
        mime: "",
        filename: host,
        size: 0,
        url,
        duration_seconds: null,
        status: "active",
      },
    ]);
    setLinkUrl("");
    setShowLink(false);
  };

  return (
    <div className="space-y-3 rounded-xl border border-slate-200 bg-slate-50/60 p-3">
      <div>
        <p className="text-sm font-bold text-[#0F4C4A]">{knowledge ? "Resources" : "Case examples (images / files)"}</p>
        <p className="text-xs text-slate-500 mt-0.5">
          {knowledge
            ? "Add examples or files Linas can use when answering."
            : "Attach visuals or documents and describe when the AI should use each one (e.g. “filled intake form”)."}
        </p>
      </div>
      {knowledge ? (
        <div className="grid grid-cols-2 gap-2">
          <button type="button" disabled={uploading} className={TEAL_BTN} onClick={() => imageRef.current?.click()}>
            Image
          </button>
          <button type="button" disabled={uploading} className={TEAL_BTN} onClick={() => videoRef.current?.click()}>
            Video
          </button>
          <button type="button" disabled={uploading} className={TEAL_BTN} onClick={() => fileRef.current?.click()}>
            File
          </button>
          <button type="button" disabled={uploading} className={TEAL_BTN} onClick={() => setShowLink(true)}>
            Link
          </button>
        </div>
      ) : null}
      {rows.map((row, index) => (
        <div key={String(row.id || index)} className="rounded-lg border border-slate-200 bg-white p-3 space-y-2">
          <div className="flex items-center justify-between gap-2 text-xs text-slate-600">
            <span>
              {String(row.kind || "file")}: {String(row.filename || row.url || row.id || "attachment")}
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
            <span className="text-sm font-medium">Title</span>
            <input
              className={FIELD_CLASS}
              value={String(row.title || "")}
              onChange={(e) => patchRow(index, { title: e.target.value })}
              placeholder="e.g. Women Before Laser Hair Removal"
              required
            />
          </label>
          <label className="block space-y-1">
            <span className="text-sm font-medium">Short description</span>
            <textarea
              className={FIELD_CLASS}
              rows={2}
              value={String(row.description || row.caption || "")}
              onChange={(e) => patchRow(index, { description: e.target.value, caption: e.target.value })}
              placeholder="Send this when the customer asks for a before-treatment example."
              required
            />
          </label>
        </div>
      ))}
      <input
        ref={imageRef}
        type="file"
        className="hidden"
        accept="image/jpeg,image/png,image/webp,image/heic,image/heif"
        onChange={(e) => void onFile(e)}
      />
      <input
        ref={videoRef}
        type="file"
        className="hidden"
        accept="video/mp4,video/quicktime,video/webm,.mp4,.mov,.webm"
        onChange={(e) => void onFile(e)}
      />
      <input
        ref={fileRef}
        type="file"
        className="hidden"
        accept="application/pdf,text/plain,text/markdown,application/json,.md,.txt,.pdf"
        onChange={(e) => void onFile(e)}
      />
      <input
        ref={careRef}
        type="file"
        className="hidden"
        accept="image/jpeg,image/png,image/webp,image/heic,image/heif,application/pdf,text/plain,text/markdown,application/json,.md,.txt,.pdf"
        onChange={(e) => void onFile(e)}
      />
      {!knowledge ? (
        <button
          type="button"
          disabled={uploading}
          onClick={() => careRef.current?.click()}
          className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 disabled:opacity-50"
        >
          {uploading ? "Uploading…" : "Attach image or file"}
        </button>
      ) : null}
      {showLink ? (
        <div className="flex gap-2">
          <input
            className={FIELD_CLASS}
            placeholder="https://"
            value={linkUrl}
            onChange={(e) => setLinkUrl(e.target.value)}
          />
          <button type="button" onClick={addLink} className="rounded-lg bg-[#107C75] px-3 py-2 text-sm text-white">
            Add
          </button>
        </div>
      ) : null}
      {uploading ? <p className="text-xs text-slate-500">Uploading…</p> : null}
    </div>
  );
}
