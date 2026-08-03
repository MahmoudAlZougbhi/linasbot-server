import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowLeftIcon, PlusIcon } from "@heroicons/react/24/outline";
import toast from "react-hot-toast";
import { useApi } from "../../hooks/useApi";

/**
 * Minimal Learning Inbox: review wrong/unclear feedback and open the same CM FAQ Add path.
 * Does not replace Bot Training until CM_FAQ_CANONICAL is enabled.
 */
const CmLearningInboxPage = () => {
  const { getWrongAnswers, getRecentFeedback, createCmFaq } = useApi();
  const navigate = useNavigate();
  const [rows, setRows] = useState(/** @type {Array<Record<string, unknown>>} */ ([]));
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [wrong, recent] = await Promise.all([getWrongAnswers(50), getRecentFeedback(50)]);
      /** @type {Array<Record<string, unknown>>} */
      const wrongList = Array.isArray(wrong?.wrong_answers)
        ? /** @type {Array<Record<string, unknown>>} */ (wrong.wrong_answers)
        : [];
      /** @type {Array<Record<string, unknown>>} */
      const recentList = Array.isArray(recent?.feedback)
        ? /** @type {Array<Record<string, unknown>>} */ (recent.feedback)
        : [];
      const unclear = recentList.filter((f) => String(f.feedback_type || "") === "unclear");
      const merged = [...wrongList, ...unclear];
      const seen = new Set();
      /** @type {Array<Record<string, unknown>>} */
      const unique = [];
      for (const item of merged) {
        const key = String(item.message_id || `${item.user_question}-${item.timestamp}`);
        if (seen.has(key)) continue;
        seen.add(key);
        unique.push(item);
      }
      setRows(unique);
    } catch {
      toast.error("Failed to load learning inbox");
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [getWrongAnswers, getRecentFeedback]);

  useEffect(() => {
    load();
  }, [load]);

  const addToFaq = async (/** @type {Record<string, unknown>} */ row) => {
    const question = String(row.user_question || "").trim();
    const answer = String(row.correct_answer || row.bot_response || "").trim();
    if (!question || !answer) {
      toast.error("Question and answer required");
      return;
    }
    const language = String(row.language || "ar");
    const result = await createCmFaq({
      question,
      answer,
      language,
      tags: ["learning_inbox", "operator_review"],
    });
    if (result?.success) {
      toast.success("Added to CM FAQ");
      navigate("/content-managers/faq");
    } else {
      toast.error(result?.error || result?.message || "Add to FAQ failed");
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <Link to="/content-managers/faq" className="inline-flex items-center gap-2 text-sm text-slate-600 mb-2">
            <ArrowLeftIcon className="h-4 w-4" />
            Back to FAQ
          </Link>
          <h1 className="text-2xl font-semibold text-slate-900">Learning Inbox</h1>
          <p className="text-sm text-slate-600 mt-1">
            Review wrong/unclear feedback and add proven answers to Content Management FAQ.
          </p>
        </div>
        <button
          type="button"
          onClick={load}
          className="rounded-lg border border-slate-200 px-3 py-2 text-sm hover:bg-slate-50"
        >
          Refresh
        </button>
      </div>

      {loading ? <p className="text-sm text-slate-500">Loading…</p> : null}
      {!loading && rows.length === 0 ? (
        <p className="text-sm text-slate-500">No wrong/unclear feedback items yet.</p>
      ) : null}

      <ul className="space-y-3">
        {rows.map((row) => (
          <li
            key={String(row.message_id || `${row.user_question}-${row.timestamp}`)}
            className="rounded-xl border border-slate-200 bg-white p-4"
          >
            <div className="text-xs uppercase tracking-wide text-slate-500 mb-2">
              {String(row.feedback_type || "feedback")} · {String(row.language || "ar")}
            </div>
            <p className="text-sm font-medium text-slate-900 whitespace-pre-wrap">{String(row.user_question || "")}</p>
            <p className="text-sm text-slate-600 mt-2 whitespace-pre-wrap">
              {String(row.correct_answer || row.bot_response || "")}
            </p>
            <button
              type="button"
              onClick={() => addToFaq(row)}
              className="mt-3 inline-flex items-center gap-2 rounded-lg bg-slate-900 px-3 py-2 text-sm text-white"
            >
              <PlusIcon className="h-4 w-4" />
              Add to FAQ
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
};

export default CmLearningInboxPage;
