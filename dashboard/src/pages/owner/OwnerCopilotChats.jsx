// @ts-nocheck
import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { toast } from 'react-hot-toast';
import { ownerApi } from './ownerApi';
import { useLoad } from './lib/useLoad';
import { formatRelative, formatDateTime } from './lib/format';
import { replyHtml } from './replyFormat';
import PageHeader from './ui/PageHeader';
import Card from './ui/Card';
import Button from './ui/Button';
import EmptyState from './ui/EmptyState';
import Alert from './ui/Alert';
import { SkeletonRows } from './ui/Skeleton';
import { ChatBubbleOvalLeftEllipsisIcon } from '@heroicons/react/24/outline';

export default function OwnerCopilotChats() {
  const state = useLoad(() => ownerApi.listTraces({ brain: 'owner_copilot' }).then((data) => data.traces || []), []);
  const [showTests, setShowTests] = useState(false);
  const [page, setPage] = useState(0);
  const [saving, setSaving] = useState(/** @type {any} */ (null));
  const [pending, setPending] = useState(false);
  const rows = useMemo(() => (state.data || []).filter((row) => showTests || row.channel !== 'brains_test'), [state.data, showTests]);
  const start = page * 25;
  const visible = rows.slice(start, start + 25);
  return (
    <div className="space-y-6">
      <PageHeader title="Copilot chats" subtitle="Questions business owners asked the Owner Copilot, and its answers." />
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={showTests} onChange={(event) => { setShowTests(event.target.checked); setPage(0); }} /> Show test chats</label>
      {state.status === 'loading' ? <SkeletonRows /> : null}
      {state.status === 'error' ? <Alert title="We couldn't load Copilot chats." detail={state.error} /> : null}
      {state.status === 'ready' && rows.length === 0 ? (
        <EmptyState icon={<ChatBubbleOvalLeftEllipsisIcon className="h-6 w-6" />} title="No Copilot chats yet" text="When a business owner asks the Copilot something, it appears here." action={<Link to="/owner/brains?ai=copilot"><Button variant="secondary">Try the Copilot</Button></Link>} />
      ) : null}
      {visible.map((row) => (
        <Card key={row.id} title={row.payload?.user_message || 'Question'}>
          <p className="text-[13px] text-slate-600" title={formatDateTime(row.created_at)}>{formatRelative(row.created_at)}</p>
          <p className="mt-2 text-sm" dir="auto" dangerouslySetInnerHTML={replyHtml(row.payload?.reply || '')} />
          <div className="mt-3 flex gap-3">
            <Button variant="secondary" onClick={() => setSaving({ question: row.payload?.user_message || '', answer: row.payload?.reply || '', source_language: 'en' })}>Save as ready answer</Button>
            <Link className="text-sm text-[#0F766E]" to={`/owner/traces?id=${row.id}`}>Technical view</Link>
          </div>
        </Card>
      ))}
      {rows.length > 25 ? <p className="text-sm">Showing {start + 1}–{Math.min(start + 25, rows.length)} of {rows.length} <Button variant="secondary" onClick={() => setPage((value) => Math.max(0, value - 1))}>Previous</Button> <Button variant="secondary" onClick={() => setPage((value) => value + 1)}>Next</Button></p> : null}
      {saving ? (
        <form className="rounded-xl border border-slate-200 bg-white p-5" onSubmit={(event) => { event.preventDefault(); setPending(true); void ownerApi.saveQa(saving).then(() => { toast.success('Saved. The Copilot will answer this instantly next time.'); setSaving(null); }).finally(() => setPending(false)); }}>
          <label className="block text-sm">Question language
            <select className="mt-1 h-9 w-full rounded-lg border border-[#7C8798] px-3" value={saving.source_language} onChange={(event) => setSaving({ ...saving, source_language: event.target.value })}>
              <option value="en">English</option><option value="ar">Arabic</option><option value="fr">French</option><option value="franco">Franco</option>
            </select>
          </label>
          <label className="mt-3 block text-sm">Question<input className="mt-1 h-9 w-full rounded-lg border border-[#7C8798] px-3" value={saving.question} onChange={(event) => setSaving({ ...saving, question: event.target.value })} /></label>
          <label className="mt-3 block text-sm">Answer<textarea className="mt-1 w-full rounded-lg border border-[#7C8798] px-3 py-2" rows={4} value={saving.answer} onChange={(event) => setSaving({ ...saving, answer: event.target.value })} /></label>
          <div className="mt-4 flex gap-2"><Button type="submit" disabled={pending}>{pending ? 'Saving…' : 'Save answer'}</Button><Button variant="secondary" onClick={() => setSaving(null)}>Cancel</Button></div>
        </form>
      ) : null}
    </div>
  );
}
