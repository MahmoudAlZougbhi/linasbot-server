// @ts-nocheck
import { useState } from 'react';
import { ownerApi } from './ownerApi';
import { useLoad } from './lib/useLoad';
import { label } from './lib/labels';
import { formatDateTime } from './lib/format';
import { replyHtml } from './replyFormat';
import PageHeader from './ui/PageHeader';
import Button from './ui/Button';
import Card from './ui/Card';
import ConfirmDialog from './ui/ConfirmDialog';
import EmptyState from './ui/EmptyState';
import Alert from './ui/Alert';
import { SkeletonRows } from './ui/Skeleton';
import { QuestionMarkCircleIcon } from '@heroicons/react/24/outline';

export default function OwnerQa() {
  const [reload, setReload] = useState(0);
  const state = useLoad(() => ownerApi.listQa().then((data) => data.items || []), [reload]);
  const [open, setOpen] = useState(false);
  const [language, setLanguage] = useState('en');
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState('');
  const [pending, setPending] = useState(/** @type {any} */ (null));
  const [shown, setShown] = useState(/** @type {Record<string, string>} */ ({}));
  return (
    <div className="space-y-6">
      <PageHeader title="Copilot answers" subtitle="Ready answers the Copilot sends instantly when an owner asks a similar question." actions={<Button onClick={() => setOpen(true)}>Add answer</Button>} />
      {state.status === 'loading' ? <SkeletonRows /> : null}
      {state.status === 'error' ? <Alert title="We couldn't load answers." detail={state.error} /> : null}
      {state.status === 'ready' && state.data.length === 0 ? <EmptyState icon={<QuestionMarkCircleIcon className="h-6 w-6" />} title="No ready answers yet" text="Save common questions here, or save one from Copilot chats." action={<Button onClick={() => setOpen(true)}>Add answer</Button>} /> : null}
      {(state.data || []).map((item) => {
        const code = shown[item.id] || item.source_language || 'en';
        const variant = (item.variants || []).find((row) => row.language === code) || item.variants?.[0] || {};
        return (
          <Card key={item.id} title={variant.question || 'Answer'} action={<Button variant="tertiary" onClick={() => setPending(item)}>Delete</Button>}>
            <p className="text-sm" dir="auto" dangerouslySetInnerHTML={replyHtml(variant.answer || '')} />
            <div className="mt-3 flex gap-2">
              {(item.variants || []).map((row) => (
                <button key={row.language} type="button" className="rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold" onClick={() => setShown((current) => ({ ...current, [item.id]: row.language }))}>{label('languageChip', row.language)}</button>
              ))}
            </div>
            <p className="mt-2 text-[13px] text-slate-600">Added {formatDateTime(item.created_at)}</p>
          </Card>
        );
      })}
      {open ? (
        <form className="rounded-xl border border-slate-200 bg-white p-5" onSubmit={(event) => { event.preventDefault(); void ownerApi.saveQa({ question, answer, source_language: language }).then(() => { setOpen(false); setReload((value) => value + 1); }); }}>
          <label className="block text-sm">Question language
            <select className="mt-1 h-9 w-full rounded-lg border border-[#7C8798] px-3" value={language} onChange={(event) => setLanguage(event.target.value)}>
              <option value="en">English</option><option value="ar">Arabic</option><option value="fr">French</option><option value="franco">Franco (Arabic in Latin letters)</option>
            </select>
          </label>
          <label className="mt-3 block text-sm">Question<input className="mt-1 h-9 w-full rounded-lg border border-[#7C8798] px-3" value={question} onChange={(event) => setQuestion(event.target.value)} /></label>
          <label className="mt-3 block text-sm">Answer<textarea className="mt-1 w-full rounded-lg border border-[#7C8798] px-3 py-2" rows={4} value={answer} onChange={(event) => setAnswer(event.target.value)} /></label>
          <p className="mt-2 text-sm text-slate-600">We save it in English, Arabic, French and Franco automatically.</p>
          <div className="mt-4 flex gap-2"><Button type="submit">Save answer</Button><Button variant="secondary" onClick={() => setOpen(false)}>Cancel</Button></div>
        </form>
      ) : null}
      {pending ? <ConfirmDialog title="Delete this answer?" body="The Copilot will stop using it. This can't be undone." confirmLabel="Delete" onClose={() => setPending(null)} onConfirm={async () => { await ownerApi.deleteQa(pending.id); setPending(null); setReload((value) => value + 1); }} /> : null}
    </div>
  );
}
