import { useEffect, useState } from "react";
import { authFetch } from "../../utils/authFetch";
import { errorMessage } from "../../utils/apiValidate";

/**
 * AI Setup Chat — patches the same CM drafts as the manual section forms.
 */
export default function CmSetupChatPanel() {
  const [intro, setIntro] = useState("");
  const [prompt, setPrompt] = useState("");
  const [currentSection, setCurrentSection] = useState("");
  const [messages, setMessages] = useState(/** @type {{role:string, content:string}[]} */ ([]));
  const [progress, setProgress] = useState(/** @type {{section:string, status:string}[]} */ ([]));
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(/** @type {string | null} */ (null));

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await authFetch("/api/cm/setup-chat/start");
        const data = await res.json();
        if (!res.ok || !data.success) {
          throw new Error(data.detail || data.error || `HTTP ${res.status}`);
        }
        if (cancelled) return;
        setIntro(data.intro || "");
        setPrompt(data.prompt || "");
        setCurrentSection(data.current_section || "");
        setProgress(Array.isArray(data.progress) ? data.progress : []);
        setMessages(Array.isArray(data.messages) ? data.messages : []);
      } catch (e) {
        if (!cancelled) setError(errorMessage(e) || "Failed to start setup chat");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const send = async () => {
    const text = input.trim();
    if (!text || busy) return;
    setBusy(true);
    setError(null);
    setInput("");
    try {
      const res = await authFetch("/api/cm/setup-chat/message", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, use_llm: true }),
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        throw new Error(data.detail || data.error || data.message || `HTTP ${res.status}`);
      }
      setMessages((prev) => [
        ...prev,
        { role: "user", content: text },
        { role: "assistant", content: data.reply || "" },
      ]);
      setCurrentSection(data.next_section || data.section || "");
      setPrompt("");
      setProgress(Array.isArray(data.progress) ? data.progress : []);
    } catch (e) {
      setError(errorMessage(e) || "Setup chat failed");
      setInput(text);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-2xl border border-slate-200 bg-white/90 p-5 shadow-sm space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-slate-800">AI Setup Assistant</h2>
        <p className="mt-1 text-sm text-slate-600 whitespace-pre-wrap">{intro}</p>
      </div>

      {progress.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {progress.map((row) => (
            <span
              key={row.section}
              className={`text-xs px-2 py-1 rounded-full ${
                row.status === "complete"
                  ? "bg-emerald-100 text-emerald-800"
                  : "bg-slate-100 text-slate-600"
              }`}
            >
              {row.section}: {row.status}
            </span>
          ))}
        </div>
      )}

      <div className="max-h-72 overflow-y-auto space-y-2 rounded-xl bg-slate-50 p-3">
        {messages.length === 0 && prompt ? (
          <p className="text-sm text-slate-700">
            <span className="font-medium">{currentSection}</span>: {prompt}
          </p>
        ) : null}
        {messages.map((m, idx) => (
          <div
            key={`${m.role}-${idx}`}
            className={`text-sm whitespace-pre-wrap rounded-lg px-3 py-2 ${
              m.role === "user" ? "bg-primary-100 text-slate-900 ml-8" : "bg-white border border-slate-200 mr-8"
            }`}
          >
            {m.content}
          </div>
        ))}
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="flex gap-2">
        <input
          className="flex-1 rounded-xl border border-slate-300 px-3 py-2 text-sm"
          value={input}
          disabled={busy}
          placeholder="أجب هنا… أو اكتب تخطي"
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") send();
          }}
        />
        <button
          type="button"
          disabled={busy}
          onClick={send}
          className="rounded-xl bg-slate-900 text-white px-4 py-2 text-sm font-medium disabled:opacity-50"
        >
          {busy ? "…" : "Send"}
        </button>
      </div>
    </div>
  );
}
