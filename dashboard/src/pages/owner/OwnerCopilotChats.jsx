import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ownerApi } from './ownerApi';
import { detectSourceLanguage, replyHtml } from './replyFormat';

export default function OwnerCopilotChats() {
  const [traces, setTraces] = useState(/** @type {any[]} */ ([]));
  const [popup, setPopup] = useState(/** @type {any} */ (null));
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState('');
  const [language, setLanguage] = useState('en');
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    ownerApi.listTraces({ brain: 'owner_copilot' })
      .then((data) => setTraces(data.traces || []))
      .catch((reason) => setError(reason.message));
  }, []);

  /** @param {any} trace */
  const openSave = (trace) => {
    const payload = trace.payload || {};
    const asked = String(payload.user_message || '');
    setQuestion(asked);
    setAnswer(String(payload.reply || ''));
    setLanguage(detectSourceLanguage(asked));
    setPopup(trace);
  };

  const save = async () => {
    setError('');
    try {
      await ownerApi.saveQa({ question, answer, source_language: language });
      setNotice('Saved to Q&A in every language.');
      setPopup(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Save failed');
    }
  };

  return (
    <div className="space-y-6">
      <header>
        <h2 className="text-2xl font-semibold">Copilot chats</h2>
        <p className="mt-1 text-sm text-slate-400">Messages the owner copilot received and answered.</p>
      </header>
      {error && <p className="rounded-lg bg-red-950 p-3 text-sm text-red-200">{error}</p>}
      {notice && <p className="rounded-lg bg-teal-950 p-3 text-sm text-teal-100">{notice}</p>}
      {traces.length === 0 ? <p className="text-sm text-slate-400">No copilot messages yet.</p> : null}
      <ul className="space-y-3">
        {traces.map((trace) => {
          const payload = trace.payload || {};
          return (
            <li key={trace.id} className="rounded-xl border border-slate-800 p-4 text-sm">
              <p className="text-slate-400">{trace.created_at} · {trace.tenant_id || 'platform'} · tokens {trace.tokens_in || 0}/{trace.tokens_out || 0}</p>
              <p className="mt-2">{payload.user_message}</p>
              <div className="mt-2 text-slate-100" dangerouslySetInnerHTML={replyHtml(payload.reply)} />
              <div className="mt-3 flex gap-3">
                <Link className="text-teal-300" to="/owner/traces">Trace</Link>
                <button type="button" className="text-teal-300" onClick={() => openSave(trace)}>Like</button>
              </div>
            </li>
          );
        })}
      </ul>
      {popup ? (
        <div className="fixed inset-0 z-40 grid place-items-center bg-slate-950/70 p-4">
          <div className="w-full max-w-lg space-y-3 rounded-xl border border-slate-700 bg-slate-900 p-5">
            <h3 className="text-lg font-semibold">Save to Q&A</h3>
            <label className="block text-sm text-slate-300">
              Language
              <select value={language} onChange={(event) => setLanguage(event.target.value)} className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2">
                <option value="en">English</option>
                <option value="ar">Arabic</option>
                <option value="fr">French</option>
                <option value="franco">Franco</option>
              </select>
            </label>
            <input value={question} onChange={(event) => setQuestion(event.target.value)} className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2" />
            <textarea value={answer} onChange={(event) => setAnswer(event.target.value)} rows={4} className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2" />
            <div className="flex gap-2">
              <button type="button" onClick={() => void save()} className="rounded-lg bg-teal-500 px-4 py-2 text-sm font-semibold text-slate-950">Save</button>
              <button type="button" onClick={() => setPopup(null)} className="rounded-lg border border-slate-600 px-4 py-2 text-sm">Cancel</button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
