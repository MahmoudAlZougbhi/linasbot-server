import { useEffect, useMemo, useState } from "react";
import { useApi } from "../hooks/useApi";
import { CheckCircleIcon, ArrowPathIcon } from "@heroicons/react/24/outline";
import toast from "react-hot-toast";

const LANGS = ["ar", "en", "fr", "franco"];

const DynamicMessagesPanel = () => {
  const { loading, getDynamicMessages, updateDynamicMessages } = useApi();
  const [data, setData] = useState(/** @type {Record<string, DynamicMessageEntry>} */ ({}));
  const [originalData, setOriginalData] = useState(/** @type {Record<string, DynamicMessageEntry>} */ ({}));
  const [refreshing, setRefreshing] = useState(false);

  const load = async () => {
    setRefreshing(true);
    const res = await getDynamicMessages();
    if (res?.success) {
      setData(res.data || {});
      setOriginalData(res.data || {});
    } else {
      toast.error(res?.error || "Failed to load dynamic messages");
    }
    setRefreshing(false);
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const changed = useMemo(
    () => JSON.stringify(data) !== JSON.stringify(originalData),
    [data, originalData]
  );

  /** @param {string} key @param {string} field @param {string} value */
  const updateField = (key, field, value) => {
    setData((prev) => ({
      ...prev,
      [key]: {
        ...(prev[key] || {}),
        [field]: value,
      },
    }));
  };

  /** @param {string} key @param {string} lang @param {string} value */
  const updateMessage = (key, lang, value) => {
    setData((prev) => ({
      ...prev,
      [key]: {
        ...(prev[key] || {}),
        messages: {
          ...((prev[key] || {}).messages || {}),
          [lang]: value,
        },
      },
    }));
  };

  const onSave = async () => {
    const res = await updateDynamicMessages(data);
    if (res?.success) {
      setOriginalData(res.data || data);
      setData(res.data || data);
      toast.success("Dynamic messages saved");
    } else {
      toast.error(res?.error || "Failed to save");
    }
  };

  const entries = Object.entries(data || {});

  return (
    <div className="space-y-6">
      <div className="card">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="font-semibold text-slate-800">Dynamic Bot Messages</h3>
            <p className="text-sm text-slate-600 mt-1">
              Edit dynamic wording used by the bot and the condition for when each one is used.
            </p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={load}
              disabled={refreshing}
              className="px-3 py-2 rounded-lg bg-slate-100 text-slate-700 hover:bg-slate-200 disabled:opacity-50 flex items-center gap-2"
            >
              <ArrowPathIcon className={`w-4 h-4 ${refreshing ? "animate-spin" : ""}`} />
              Refresh
            </button>
            <button
              onClick={onSave}
              disabled={loading || !changed}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 flex items-center gap-2"
            >
              <CheckCircleIcon className="w-4 h-4" />
              Save Changes
            </button>
          </div>
        </div>
      </div>

      {entries.map(([key, item]) => (
        <div key={key} className="card space-y-4">
          <div>
            <p className="text-xs text-slate-500 font-mono">{key}</p>
            <input
              value={item?.label || ""}
              onChange={(e) => updateField(key, "label", e.target.value)}
              className="mt-1 w-full p-2 border border-slate-200 rounded-lg text-sm font-medium"
              placeholder="Display name"
            />
          </div>

          <div>
            <label className="text-sm font-medium text-slate-700">When used</label>
            <textarea
              value={item?.when_used || ""}
              onChange={(e) => updateField(key, "when_used", e.target.value)}
              className="mt-1 w-full p-3 border border-slate-200 rounded-lg text-sm h-20"
              placeholder="Explain when this message is used..."
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {LANGS.map((lang) => (
              <div key={`${key}-${lang}`}>
                <label className="text-xs font-semibold uppercase text-slate-500">{lang}</label>
                <textarea
                  value={item?.messages?.[lang] || ""}
                  onChange={(e) => updateMessage(key, lang, e.target.value)}
                  className="mt-1 w-full p-3 border border-slate-200 rounded-lg text-sm h-24"
                />
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
};

export default DynamicMessagesPanel;
