import { useEffect, useState } from 'react';
import { ownerApi } from './ownerApi';

export default function OwnerKnowledge() {
  const [entries, setEntries] = useState(/** @type {any[]} */ ([]));
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [editing, setEditing] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const load = () => {
    ownerApi.listKnowledge().then((data) => setEntries(data.entries || [])).catch((reason) => setError(reason.message));
  };

  useEffect(() => { load(); }, []);

  const save = async () => {
    setError('');
    setNotice('');
    try {
      await ownerApi.saveKnowledge({ title, body, id: editing || undefined });
      setTitle('');
      setBody('');
      setEditing('');
      setNotice('Saved. The entry was re-embedded for the owner copilot.');
      load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Save failed');
    }
  };

  return (
    <div className="space-y-6">
      <header>
        <h2 className="text-2xl font-semibold">Owner copilot knowledge</h2>
        <p className="mt-1 text-sm text-slate-400">Add the app facts the copilot may use. Saving rebuilds the search index. A question receives only the closest entries.</p>
      </header>
      {error && <p className="rounded-lg bg-red-950 p-3 text-sm text-red-200">{error}</p>}
      {notice && <p className="rounded-lg bg-teal-950 p-3 text-sm text-teal-100">{notice}</p>}
      <div className="space-y-3 rounded-xl border border-slate-800 bg-slate-900 p-4">
        <input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Title" className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2" />
        <textarea value={body} onChange={(event) => setBody(event.target.value)} placeholder="What should the copilot know?" rows={5} className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2" />
        <button type="button" onClick={() => void save()} className="rounded-lg bg-teal-500 px-4 py-2 text-sm font-semibold text-slate-950">Save</button>
      </div>
      {entries.length === 0 ? <p className="text-sm text-slate-400">No knowledge entries yet.</p> : null}
      <ul className="space-y-3">
        {entries.map((entry) => (
          <li key={entry.id} className="rounded-xl border border-slate-800 p-4">
            <p className="font-medium">{entry.title}</p>
            <p className="mt-2 whitespace-pre-wrap text-sm text-slate-300">{entry.body}</p>
            <div className="mt-3 flex gap-3 text-sm">
              <button type="button" className="text-teal-300" onClick={() => { setEditing(entry.id); setTitle(entry.title); setBody(entry.body); }}>Edit</button>
              <button type="button" className="text-red-300" onClick={() => void ownerApi.deleteKnowledge(entry.id).then(load)}>Delete</button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
