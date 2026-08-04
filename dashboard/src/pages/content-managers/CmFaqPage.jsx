import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  ArrowLeftIcon,
  ArchiveBoxIcon,
  ArrowPathIcon,
  CheckCircleIcon,
  MagnifyingGlassIcon,
  PlusIcon,
} from "@heroicons/react/24/outline";
import toast from "react-hot-toast";
import { useApi } from "../../hooks/useApi";

const LANGS = [
  { id: "ar", label: "Arabic" },
  { id: "en", label: "English" },
  { id: "fr", label: "French" },
  { id: "franco", label: "Franco → Arabic answer" },
];

/**
 * Professional FAQ control plane (no JSON for normal workflow).
 * Canonical owner-facing FAQ management inside Content Management.
 */
const CmFaqPage = () => {
  const {
    listCmFaq,
    createCmFaq,
    archiveCmFaq,
    patchCmFaqVariant,
    regenerateCmFaq,
    getCmMeta,
    loading,
  } = useApi();

  const [items, setItems] = useState(/** @type {Array<Record<string, unknown>>} */ ([]));
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [langFilter, setLangFilter] = useState("all");
  const [selectedId, setSelectedId] = useState(/** @type {string | null} */ (null));
  const [activeLang, setActiveLang] = useState("ar");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [newQuestion, setNewQuestion] = useState("");
  const [newAnswer, setNewAnswer] = useState("");
  const [newLanguage, setNewLanguage] = useState("ar");
  const [runtimeMode, setRuntimeMode] = useState("legacy");
  const [publishEnabled, setPublishEnabled] = useState(false);

  const selected = useMemo(
    () => items.find((item) => String(item.qa_group_id) === selectedId) || null,
    [items, selectedId]
  );

  const selectedVariant = useMemo(() => {
    const variants = Array.isArray(selected?.variants) ? selected.variants : [];
    return (
      variants.find((v) => v && typeof v === "object" && /** @type {{language?: string}} */ (v).language === activeLang) ||
      null
    );
  }, [selected, activeLang]);

  const [editQuestion, setEditQuestion] = useState("");
  const [editAnswer, setEditAnswer] = useState("");

  useEffect(() => {
    const variant = selectedVariant && typeof selectedVariant === "object" ? selectedVariant : null;
    setEditQuestion(variant && "question" in variant ? String(variant.question || "") : "");
    setEditAnswer(variant && "answer" in variant ? String(variant.answer || "") : "");
  }, [selectedVariant, selectedId, activeLang]);

  const load = useCallback(async () => {
    const [faqRes, metaRes] = await Promise.all([
      listCmFaq({
        q: query || undefined,
        status: statusFilter === "all" ? undefined : statusFilter,
        language: langFilter === "all" ? undefined : langFilter,
        include_archived: statusFilter === "archived" || statusFilter === "restricted",
      }),
      getCmMeta(),
    ]);
    if (metaRes?.runtime_mode) setRuntimeMode(String(metaRes.runtime_mode));
    setPublishEnabled(Boolean(metaRes?.publish_enabled));
    if (faqRes?.success && Array.isArray(faqRes.data)) {
      setItems(/** @type {Array<Record<string, unknown>>} */ (faqRes.data));
      if (!selectedId && faqRes.data[0]?.qa_group_id) {
        setSelectedId(String(faqRes.data[0].qa_group_id));
      }
    } else {
      toast.error(faqRes?.error || "Failed to load FAQ");
    }
  }, [getCmMeta, langFilter, listCmFaq, query, selectedId, statusFilter]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleCreate = async () => {
    if (!newQuestion.trim() || !newAnswer.trim()) {
      toast.error("Question and answer are required");
      return;
    }
    const res = await createCmFaq({
      question: newQuestion.trim(),
      answer: newAnswer.trim(),
      language: newLanguage,
    });
    if (!res?.success) {
      toast.error(res?.error || "Could not create FAQ");
      return;
    }
    if (Array.isArray(res.duplicates) && res.duplicates.length > 0) {
      toast(`Saved, but ${res.duplicates.length} similar FAQ group(s) already exist`, { icon: "⚠️" });
    } else {
      toast.success("FAQ group created in 4 languages (draft)");
    }
    setNewQuestion("");
    setNewAnswer("");
    if (res.qa_group_id) setSelectedId(String(res.qa_group_id));
    await load();
  };

  const handleSaveVariant = async () => {
    if (!selectedId) return;
    const res = await patchCmFaqVariant(selectedId, activeLang, {
      question: editQuestion,
      answer: editAnswer,
    });
    if (!res?.success) {
      toast.error(res?.error || "Save failed");
      return;
    }
    toast.success("Variant updated");
    await load();
  };

  const handleRegenerate = async () => {
    if (!selectedId) return;
    const res = await regenerateCmFaq(selectedId, {});
    if (!res?.success) {
      toast.error(res?.error || "Regenerate failed — nothing fake was saved");
      return;
    }
    toast.success("Variants regenerated from source language");
    await load();
  };

  const handleArchive = async () => {
    if (!selectedId) return;
    const res = await archiveCmFaq(selectedId);
    if (!res?.success) {
      toast.error(res?.error || "Archive failed");
      return;
    }
    toast.success("FAQ group archived");
    setSelectedId(null);
    await load();
  };

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <Link to="/content-managers" className="inline-flex items-center text-sm text-slate-500 hover:text-slate-800 mb-2">
            <ArrowLeftIcon className="w-4 h-4 mr-1" /> Content Managers
          </Link>
          <h1 className="text-2xl font-semibold text-slate-900">FAQ</h1>
          <p className="text-slate-600 mt-1 max-w-3xl">
            Teach the AI with linked Arabic / English / French / Franco questions. Franco questions keep Latin script;
            answers for Arabic and Franco are always Arabic script. This is FAQ authoring — not model retraining.
          </p>
        </div>
        <div className="text-xs text-slate-500 space-y-1 text-right">
          <div>Runtime: {runtimeMode}</div>
          <div>Publish: {publishEnabled ? "enabled" : "drafts only"}</div>
          <Link to="/content-managers/learning-inbox" className="text-slate-700 hover:underline block">
            Learning Inbox →
          </Link>
          <Link to="/content-managers/publish" className="text-emerald-700 hover:underline">
            Preview / Validate / Publish →
          </Link>
        </div>
      </div>

      <div className="grid lg:grid-cols-5 gap-4">
        <motion.section layout className="lg:col-span-2 rounded-2xl border border-slate-200 bg-white p-4 space-y-3">
          <div className="flex gap-2">
            <div className="relative flex-1">
              <MagnifyingGlassIcon className="w-4 h-4 absolute left-3 top-3 text-slate-400" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search questions or answers"
                className="w-full rounded-xl border border-slate-200 pl-9 pr-3 py-2 text-sm"
              />
            </div>
          </div>
          <div className="flex gap-2">
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="rounded-xl border border-slate-200 px-3 py-2 text-sm"
            >
              <option value="all">All statuses</option>
              <option value="draft">Draft</option>
              <option value="active">Active</option>
              <option value="archived">Archived</option>
              <option value="restricted">Restricted</option>
            </select>
            <select
              value={langFilter}
              onChange={(e) => setLangFilter(e.target.value)}
              className="rounded-xl border border-slate-200 px-3 py-2 text-sm"
            >
              <option value="all">All languages</option>
              {LANGS.map((lang) => (
                <option key={lang.id} value={lang.id}>
                  {lang.label}
                </option>
              ))}
            </select>
          </div>

          <div className="max-h-[28rem] overflow-auto divide-y divide-slate-100 border border-slate-100 rounded-xl">
            {items.map((item) => {
              const id = String(item.qa_group_id || "");
              const variants = Array.isArray(item.variants) ? item.variants : [];
              const preview =
                variants.find((v) => v && typeof v === "object" && /** @type {{language?: string}} */ (v).language === "en") ||
                variants[0];
              const previewQ =
                preview && typeof preview === "object" && "question" in preview
                  ? String(/** @type {{question?: string}} */ (preview).question || "")
                  : "(empty)";
              return (
                <button
                  key={id}
                  type="button"
                  onClick={() => setSelectedId(id)}
                  className={`w-full text-left px-3 py-3 hover:bg-slate-50 ${
                    selectedId === id ? "bg-slate-50" : ""
                  }`}
                >
                  <div className="text-sm font-medium text-slate-800 line-clamp-2">{previewQ}</div>
                  <div className="mt-1 flex gap-2 text-[11px] text-slate-500">
                    <span>{String(item.status || "draft")}</span>
                    {item.incomplete ? <span className="text-amber-700">incomplete</span> : <span>4 languages</span>}
                    {item.reviewed ? <span className="text-emerald-700">reviewed</span> : null}
                  </div>
                </button>
              );
            })}
            {!items.length && <div className="p-4 text-sm text-slate-500">No FAQ groups yet.</div>}
          </div>
        </motion.section>

        <section className="lg:col-span-3 space-y-4">
          <div className="rounded-2xl border border-slate-200 bg-white p-4 space-y-3">
            <h2 className="font-medium text-slate-900 flex items-center gap-2">
              <PlusIcon className="w-4 h-4" /> Add Q&A group
            </h2>
            <p className="text-xs text-slate-500">
              Write in any supported language. We create the linked 4-language group automatically. Numbers, prices,
              branch names, and phones are preserved — never invented.
            </p>
            <select
              value={newLanguage}
              onChange={(e) => setNewLanguage(e.target.value)}
              className="rounded-xl border border-slate-200 px-3 py-2 text-sm"
            >
              {LANGS.map((lang) => (
                <option key={lang.id} value={lang.id}>
                  Source: {lang.label}
                </option>
              ))}
            </select>
            <textarea
              value={newQuestion}
              onChange={(e) => setNewQuestion(e.target.value)}
              placeholder="Question"
              className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm min-h-[70px]"
            />
            <textarea
              value={newAnswer}
              onChange={(e) => setNewAnswer(e.target.value)}
              placeholder="Answer"
              className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm min-h-[90px]"
            />
            <button
              type="button"
              disabled={loading}
              onClick={() => void handleCreate()}
              className="rounded-xl bg-slate-900 text-white px-4 py-2 text-sm disabled:opacity-50"
            >
              Save as draft (4 languages)
            </button>
          </div>

          {selected ? (
            <div className="rounded-2xl border border-slate-200 bg-white p-4 space-y-3">
              <div className="flex items-center justify-between gap-2 flex-wrap">
                <h2 className="font-medium text-slate-900">Edit linked variants</h2>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => void handleRegenerate()}
                    className="inline-flex items-center gap-1 rounded-xl border border-slate-200 px-3 py-1.5 text-sm"
                  >
                    <ArrowPathIcon className="w-4 h-4" /> Regenerate missing
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleArchive()}
                    className="inline-flex items-center gap-1 rounded-xl border border-rose-200 text-rose-700 px-3 py-1.5 text-sm"
                  >
                    <ArchiveBoxIcon className="w-4 h-4" /> Archive
                  </button>
                </div>
              </div>

              <div className="flex flex-wrap gap-2">
                {LANGS.map((lang) => (
                  <button
                    key={lang.id}
                    type="button"
                    onClick={() => setActiveLang(lang.id)}
                    className={`rounded-full px-3 py-1 text-xs border ${
                      activeLang === lang.id
                        ? "bg-slate-900 text-white border-slate-900"
                        : "bg-white text-slate-700 border-slate-200"
                    }`}
                  >
                    {lang.label}
                  </button>
                ))}
              </div>

              <textarea
                value={editQuestion}
                onChange={(e) => setEditQuestion(e.target.value)}
                className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm min-h-[70px]"
                placeholder="Question"
              />
              <textarea
                value={editAnswer}
                onChange={(e) => setEditAnswer(e.target.value)}
                className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm min-h-[90px]"
                placeholder="Answer"
              />
              <div className="flex items-center gap-3 flex-wrap">
                <button
                  type="button"
                  onClick={() => void handleSaveVariant()}
                  className="inline-flex items-center gap-1 rounded-xl bg-emerald-700 text-white px-4 py-2 text-sm"
                >
                  <CheckCircleIcon className="w-4 h-4" /> Save variant
                </button>
                <button
                  type="button"
                  onClick={() => setShowAdvanced((v) => !v)}
                  className="text-xs text-slate-500 underline"
                >
                  {showAdvanced ? "Hide" : "Show"} advanced diagnostics
                </button>
              </div>
              {showAdvanced ? (
                <div className="text-xs text-slate-500 rounded-xl bg-slate-50 p-3 break-all">
                  Internal group id: {String(selected.qa_group_id)}
                </div>
              ) : null}
              {selected.incomplete ? (
                <div className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-xl px-3 py-2">
                  This group is incomplete (missing one or more of the 4 languages). It stays draft until complete.
                </div>
              ) : null}
            </div>
          ) : (
            <div className="rounded-2xl border border-dashed border-slate-200 p-8 text-sm text-slate-500">
              Select a FAQ group to edit its language variants.
            </div>
          )}
        </section>
      </div>
    </div>
  );
};

export default CmFaqPage;
