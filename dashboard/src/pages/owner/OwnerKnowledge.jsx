// @ts-nocheck
import { useState } from 'react';
import { ownerApi } from './ownerApi';
import { useLoad } from './lib/useLoad';
import PageHeader from './ui/PageHeader';
import Button from './ui/Button';
import Card from './ui/Card';
import ConfirmDialog from './ui/ConfirmDialog';
import EmptyState from './ui/EmptyState';
import Alert from './ui/Alert';
import { SkeletonRows } from './ui/Skeleton';
import { BookOpenIcon } from '@heroicons/react/24/outline';

export default function OwnerKnowledge() {
  const [reload, setReload] = useState(0);
  const state = useLoad(() => ownerApi.listKnowledge().then((data) => data.entries || []), [reload]);
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [pending, setPending] = useState(/** @type {any} */ (null));
  const [error, setError] = useState('');
  return (
    <div className="space-y-6">
      <PageHeader title="Copilot knowledge" subtitle="Facts the Owner Copilot uses to answer business owners' questions about the app." actions={state.status === 'ready' && state.data.length > 0 ? <Button onClick={() => setOpen(true)}>Add knowledge</Button> : null} />
      {state.status === 'loading' ? <SkeletonRows /> : null}
      {state.status === 'error' ? <Alert title="We couldn't load knowledge." detail={state.error} /> : null}
      {state.status === 'ready' && state.data.length === 0 ? <EmptyState icon={<BookOpenIcon className="h-6 w-6" />} title="No knowledge yet" text="Add facts about the app so the Copilot answers owners correctly." action={<Button onClick={() => setOpen(true)}>Add knowledge</Button>} /> : null}
      <div className="grid gap-4 xl:grid-cols-2">
        {(state.data || []).map((entry) => (
          <Card key={entry.id} title={entry.title} action={<Button variant="tertiary" onClick={() => setPending(entry)}>Delete</Button>}>
            <p className="text-sm text-slate-700">{entry.body}</p>
          </Card>
        ))}
      </div>
      {open ? (
        <div className="fixed inset-0 z-40 flex justify-end bg-slate-900/40">
          <form className="h-full w-full max-w-[560px] bg-white p-5" onSubmit={(event) => { event.preventDefault(); void ownerApi.saveKnowledge({ title, body }).then(() => { setOpen(false); setReload((value) => value + 1); }).catch((reason) => setError(reason.message)); }}>
            <h2 className="text-base font-semibold">Add knowledge</h2>
            <label className="mt-4 block text-sm">Title<input className="mt-1 h-9 w-full rounded-lg border border-[#7C8798] px-3" value={title} onChange={(event) => setTitle(event.target.value)} /></label>
            <label className="mt-4 block text-sm">Details<textarea className="mt-1 w-full rounded-lg border border-[#7C8798] px-3 py-2" rows={8} value={body} onChange={(event) => setBody(event.target.value)} /></label>
            {error ? <p className="mt-2 text-sm text-red-800">{error}</p> : null}
            <div className="mt-4 flex gap-2"><Button type="submit">Save</Button><Button variant="secondary" onClick={() => setOpen(false)}>Cancel</Button></div>
          </form>
        </div>
      ) : null}
      {pending ? <ConfirmDialog title={`Delete "${pending.title}"?`} body="The Copilot will stop using this. This can't be undone." confirmLabel="Delete" onClose={() => setPending(null)} onConfirm={async () => { await ownerApi.deleteKnowledge(pending.id); setPending(null); setReload((value) => value + 1); }} /> : null}
    </div>
  );
}
