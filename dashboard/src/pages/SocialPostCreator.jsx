import { useCallback, useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  PhotoIcon,
  SparklesIcon,
  ArrowPathIcon,
  EyeIcon,
  PaperAirplaneIcon,
  CheckCircleIcon,
} from "@heroicons/react/24/outline";
import toast from "react-hot-toast";
import { authFetch } from "../utils/authFetch";
import { errorMessage } from "../utils/apiValidate";

/**
 * @typedef {Object} SocialAsset
 * @property {string} binding_id
 * @property {string} channel
 * @property {string} page_name
 * @property {string} instagram_username
 * @property {boolean} publish_scopes_ready
 */

export default function SocialPostCreator() {
  const [loadingAssets, setLoadingAssets] = useState(true);
  /** @type {[SocialAsset[], Function]} */
  const [facebookPages, setFacebookPages] = useState([]);
  /** @type {[SocialAsset[], Function]} */
  const [instagramAccounts, setInstagramAccounts] = useState([]);
  const [publishFacebook, setPublishFacebook] = useState(false);
  const [publishInstagram, setPublishInstagram] = useState(false);
  const [facebookBindingId, setFacebookBindingId] = useState("");
  const [instagramBindingId, setInstagramBindingId] = useState("");
  const [caption, setCaption] = useState("");
  const [topic, setTopic] = useState("");
  const [mediaId, setMediaId] = useState("");
  const [mediaPreviewUrl, setMediaPreviewUrl] = useState("");
  const [generating, setGenerating] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [previewToken, setPreviewToken] = useState("");
  const [previewData, setPreviewData] = useState(null);
  const [publishResults, setPublishResults] = useState(null);
  const [confirmPublish, setConfirmPublish] = useState(false);

  const loadAssets = useCallback(async () => {
    setLoadingAssets(true);
    try {
      const response = await authFetch("/api/meta/social-posts/assets");
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Could not load Meta assets");
      const fb = Array.isArray(data.facebook_pages) ? data.facebook_pages : [];
      const ig = Array.isArray(data.instagram_accounts) ? data.instagram_accounts : [];
      setFacebookPages(fb);
      setInstagramAccounts(ig);
      if (!facebookBindingId && fb[0]) setFacebookBindingId(fb[0].binding_id);
      if (!instagramBindingId && ig[0]) setInstagramBindingId(ig[0].binding_id);
    } catch (error) {
      toast.error(errorMessage(error) || "Could not load Meta assets");
    } finally {
      setLoadingAssets(false);
    }
  }, [facebookBindingId, instagramBindingId]);

  useEffect(() => {
    loadAssets();
  }, [loadAssets]);

  const selectedFacebook = useMemo(
    () => facebookPages.find((row) => row.binding_id === facebookBindingId),
    [facebookPages, facebookBindingId],
  );
  const selectedInstagram = useMemo(
    () => instagramAccounts.find((row) => row.binding_id === instagramBindingId),
    [instagramAccounts, instagramBindingId],
  );

  const canGenerate = publishFacebook || publishInstagram;
  const canPreview = caption.trim().length > 0 && canGenerate;
  const canPublish = Boolean(previewToken) && confirmPublish;

  const handleGenerateCaption = async () => {
    if (!canGenerate) {
      toast.error("Select at least one platform");
      return;
    }
    setGenerating(true);
    setPreviewToken("");
    setPreviewData(null);
    setPublishResults(null);
    setConfirmPublish(false);
    try {
      const platforms = [];
      if (publishFacebook) platforms.push("facebook");
      if (publishInstagram) platforms.push("instagram");
      const response = await authFetch("/api/meta/social-posts/generate-caption", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topic, platforms }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Caption generation failed");
      setCaption(data.caption || "");
      toast.success("Caption generated — review and edit before publishing");
    } catch (error) {
      toast.error(errorMessage(error) || "Caption generation failed");
    } finally {
      setGenerating(false);
    }
  };

  const fileToBase64 = (file) =>
    new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const result = String(reader.result || "");
        const base64 = result.includes(",") ? result.split(",")[1] : result;
        resolve(base64);
      };
      reader.onerror = () => reject(reader.error || new Error("Could not read file"));
      reader.readAsDataURL(file);
    });

  const handleMediaChange = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setPreviewToken("");
    setPreviewData(null);
    setPublishResults(null);
    setConfirmPublish(false);
    try {
      const content_base64 = await fileToBase64(file);
      const response = await authFetch("/api/meta/social-posts/upload-media", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          filename: file.name,
          content_type: file.type,
          content_base64,
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Upload failed");
      setMediaId(data.media_id || "");
      setMediaPreviewUrl(URL.createObjectURL(file));
      toast.success("Image uploaded");
    } catch (error) {
      toast.error(errorMessage(error) || "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const handlePreview = async () => {
    if (!canPreview) return;
    if (publishInstagram && !mediaId) {
      toast.error("Instagram posts require an image");
      return;
    }
    setPreviewing(true);
    setPublishResults(null);
    setConfirmPublish(false);
    try {
      const response = await authFetch("/api/meta/social-posts/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          publish_facebook: publishFacebook,
          publish_instagram: publishInstagram,
          facebook_binding_id: facebookBindingId,
          instagram_binding_id: instagramBindingId,
          caption,
          media_id: mediaId,
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Preview failed");
      setPreviewToken(data.preview_token || "");
      setPreviewData(data.preview || null);
      toast.success("Preview ready — confirm to publish");
    } catch (error) {
      toast.error(errorMessage(error) || "Preview failed");
    } finally {
      setPreviewing(false);
    }
  };

  const handlePublish = async () => {
    if (!canPublish) return;
    setPublishing(true);
    try {
      const response = await authFetch("/api/meta/social-posts/publish", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ preview_token: previewToken, confirmed: true }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Publish failed");
      setPublishResults(data.results || []);
      if (data.success) {
        toast.success("Post published");
      } else {
        toast.error("One or more platforms failed to publish");
      }
    } catch (error) {
      toast.error(errorMessage(error) || "Publish failed");
    } finally {
      setPublishing(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">Create Post</h1>
        <p className="text-sm text-slate-600 mt-1">
          Generate a caption with AI, review it, preview, then publish explicitly. AI never publishes automatically.
        </p>
      </div>

      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        className="bg-white/80 backdrop-blur border border-white/60 rounded-2xl shadow-sm p-6 space-y-6"
      >
        <section>
          <h2 className="text-sm font-semibold text-slate-700 mb-3">Platforms</h2>
          <div className="flex flex-wrap gap-4">
            <label className="inline-flex items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={publishFacebook}
                onChange={(e) => setPublishFacebook(e.target.checked)}
                disabled={loadingAssets || facebookPages.length === 0}
              />
              Facebook
            </label>
            <label className="inline-flex items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={publishInstagram}
                onChange={(e) => setPublishInstagram(e.target.checked)}
                disabled={loadingAssets || instagramAccounts.length === 0}
              />
              Instagram
            </label>
          </div>
          {publishFacebook && (
            <div className="mt-3">
              <label className="block text-xs font-medium text-slate-600 mb-1">Facebook Page</label>
              <select
                className="w-full max-w-md rounded-lg border border-slate-200 px-3 py-2 text-sm"
                value={facebookBindingId}
                onChange={(e) => setFacebookBindingId(e.target.value)}
              >
                {facebookPages.map((page) => (
                  <option key={page.binding_id} value={page.binding_id}>
                    {page.page_name || page.binding_id}
                    {!page.publish_scopes_ready ? " (re-authorize for publish)" : ""}
                  </option>
                ))}
              </select>
            </div>
          )}
          {publishInstagram && (
            <div className="mt-3">
              <label className="block text-xs font-medium text-slate-600 mb-1">Instagram account</label>
              <select
                className="w-full max-w-md rounded-lg border border-slate-200 px-3 py-2 text-sm"
                value={instagramBindingId}
                onChange={(e) => setInstagramBindingId(e.target.value)}
              >
                {instagramAccounts.map((account) => (
                  <option key={account.binding_id} value={account.binding_id}>
                    @{account.instagram_username || account.binding_id}
                    {!account.publish_scopes_ready ? " (re-authorize for publish)" : ""}
                  </option>
                ))}
              </select>
            </div>
          )}
        </section>

        <section>
          <h2 className="text-sm font-semibold text-slate-700 mb-3">Caption</h2>
          <label className="block text-xs font-medium text-slate-600 mb-1">Topic or brief (optional)</label>
          <input
            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm mb-3"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="e.g. summer skincare tips"
          />
          <textarea
            className="w-full min-h-[140px] rounded-lg border border-slate-200 px-3 py-2 text-sm"
            value={caption}
            onChange={(e) => {
              setCaption(e.target.value);
              setPreviewToken("");
              setPreviewData(null);
              setConfirmPublish(false);
            }}
            placeholder="Write or generate your caption…"
          />
          <div className="flex flex-wrap gap-2 mt-3">
            <button
              type="button"
              onClick={handleGenerateCaption}
              disabled={generating || !canGenerate}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary-600 text-white text-sm disabled:opacity-50"
            >
              <SparklesIcon className="w-4 h-4" />
              {generating ? "Generating…" : "Generate with AI"}
            </button>
            <button
              type="button"
              onClick={handleGenerateCaption}
              disabled={generating || !canGenerate || !caption}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-slate-200 text-slate-700 text-sm disabled:opacity-50"
            >
              <ArrowPathIcon className="w-4 h-4" />
              Regenerate
            </button>
          </div>
        </section>

        <section>
          <h2 className="text-sm font-semibold text-slate-700 mb-3">Media</h2>
          <p className="text-xs text-slate-500 mb-2">JPEG or PNG up to 8 MB. Required for Instagram.</p>
          <label className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-dashed border-slate-300 text-sm text-slate-700 cursor-pointer">
            <PhotoIcon className="w-4 h-4" />
            {uploading ? "Uploading…" : "Upload image"}
            <input type="file" accept="image/jpeg,image/png" className="hidden" onChange={handleMediaChange} />
          </label>
          {mediaPreviewUrl && (
            <img src={mediaPreviewUrl} alt="Preview" className="mt-3 max-h-48 rounded-lg border border-slate-200" />
          )}
        </section>

        <section className="flex flex-wrap gap-3">
          <button
            type="button"
            onClick={handlePreview}
            disabled={previewing || !canPreview}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-800 text-white text-sm disabled:opacity-50"
          >
            <EyeIcon className="w-4 h-4" />
            {previewing ? "Building preview…" : "Preview"}
          </button>
        </section>

        {previewData && (
          <section className="rounded-xl border border-slate-200 bg-slate-50 p-4 space-y-3">
            <h3 className="text-sm font-semibold text-slate-800">Preview</h3>
            <p className="text-sm text-slate-700 whitespace-pre-wrap">{previewData.caption}</p>
            <ul className="text-xs text-slate-600 space-y-1">
              {previewData.publish_facebook && <li>Facebook: {previewData.facebook_page_name || selectedFacebook?.page_name}</li>}
              {previewData.publish_instagram && (
                <li>Instagram: @{previewData.instagram_username || selectedInstagram?.instagram_username}</li>
              )}
            </ul>
            <label className="inline-flex items-center gap-2 text-sm text-slate-700">
              <input type="checkbox" checked={confirmPublish} onChange={(e) => setConfirmPublish(e.target.checked)} />
              I reviewed this caption and confirm publishing
            </label>
            <button
              type="button"
              onClick={handlePublish}
              disabled={publishing || !canPublish}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-600 text-white text-sm disabled:opacity-50"
            >
              <PaperAirplaneIcon className="w-4 h-4" />
              {publishing ? "Publishing…" : "Publish"}
            </button>
          </section>
        )}

        {publishResults && (
          <section className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 space-y-2">
            <h3 className="text-sm font-semibold text-emerald-900 flex items-center gap-2">
              <CheckCircleIcon className="w-4 h-4" />
              Publish results
            </h3>
            {publishResults.map((row) => (
              <div key={row.platform} className="text-sm text-emerald-900">
                <strong>{row.platform}</strong>: {row.success ? "success" : row.error || "failed"}
                {row.permalink ? (
                  <>
                    {" "}
                    —{" "}
                    <a href={row.permalink} target="_blank" rel="noreferrer" className="underline">
                      View post
                    </a>
                  </>
                ) : null}
              </div>
            ))}
          </section>
        )}
      </motion.div>
    </div>
  );
}
