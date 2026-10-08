import { useEffect, useState } from 'react';
import { ownerApi } from './ownerApi';

export default function OwnerQa() {
  const [items, setItems] = useState(/** @type {any[]} */ ([]));
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState('');
  const [language, setLanguage] = useState('en');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const load = () => ownerApi.listQa().then((data) => setItems(data.items || [])).catch((reason) => setError(reason.message));
  useEffect(() => {
    ownerApi.listQa().then((data) => setItems(data.items || [])).catch((reason) => setError(reason.message));
  }, []);

  const save = async () => {
    setError('');
    try {
      await ownerApi.saveQa({ question, answer, source_language: language });
      setQuestion('');
      setAnswer('');
      setNotice('Saved in Arabic, English, French, and Franco, each with its own embedding.');
      load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Save failed');
    }
  };

  return (
    <div className="space-y-6">
      <header>
        <h2 className="text-2xl font-semibold">Owner copilot Q&A</h2>
        <p className="mt-1 text-sm text-slate-400">A close question in any supported language is answered from here, without a model call.</p>
      </header>
      {error && <p className="rounded-lg bg-red-950 p-3 text-sm text-red-200">{error}</p>}
      {notice && <p className="rounded-lg bg-teal-950 p-3 text-sm text-teal-100">{notice}</p>}
      <div className="space-y-3 rounded-xl border border-slate-800 bg-slate-900 p-4">
        <select value={language} onChange={(event) => setLanguage(event.target.value)} className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2">
          <option value="en">English</option>
          <option value="ar">Arabic</option>
          <option value="fr">French</option>
          <option value="franco">Franco</option>
        </select>
        <input value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Question" className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2" />
        <textarea value={answer} onChange={(event) => setAnswer(event.target.value)} placeholder="Answer" rows={4} className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2" />
        <button type="button" onClick={() => void save()} className="rounded-lg bg-teal-500 px-4 py-2 text-sm font-semibold text-slate-950">Save Q&A</button>
      </div>
      {items.length === 0 ? <p className="text-sm text-slate-400">No saved answers yet.</p> : null}
      <ul className="space-y-3">
        {items.map((item) => (
          <li key={item.id} className="rounded-xl border border-slate-800 p-4 text-sm">
            {(item.variants || []).map((/** @type {any} */ variant) => (
              <p key={variant.language} className="mt-2"><span className="text-teal-300">{variant.language}:</span> {variant.question}</p>
            ))}
            <button
              type="button"
              className="mt-3 text-sm text-red-300"
              onClick={() => {
                if (window.confirm('Delete this Q&A?')) {
                  void ownerApi.deleteQa(item.id).then(load).catch((reason) => setError(reason.message));
                }
              }}
            >
              Delete
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
