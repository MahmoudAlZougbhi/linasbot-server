// @ts-nocheck
import { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ownerApi } from './ownerApi';
import { replyHtml } from './replyFormat';
import PageHeader from './ui/PageHeader';
import Button from './ui/Button';
import TechDetails from './ui/TechDetails';
import EmptyState from './ui/EmptyState';
import { SparklesIcon, UserIcon } from '@heroicons/react/24/outline';

/** @typedef {{ role: 'user' | 'assistant' | 'status', text: string }} BrainLine */

export default function OwnerBrains() {
  const [params, setParams] = useSearchParams();
  const [subscribers, setSubscribers] = useState(/** @type {any[]} */ ([]));
  const [loadingTenants, setLoadingTenants] = useState(true);
  const [draftMode, setDraftMode] = useState(false);
  const [error, setError] = useState('');
  const [customer, setCustomer] = useState(/** @type {BrainLine[]} */ ([]));
  const [copilot, setCopilot] = useState(/** @type {BrainLine[]} */ ([]));
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState('');
  const tenantId = params.get('tenant') || '';
  const ai = params.get('ai') === 'copilot' ? 'copilot' : 'customer';
  const tenantRef = useRef(tenantId);
  tenantRef.current = tenantId;

  useEffect(() => {
    let live = true;
    ownerApi.subscribers()
      .then((data) => {
        if (!live) return;
        const rows = (data.subscribers || []).filter((row) => !row.hide_by_default);
        setSubscribers(rows);
        if (!params.get('tenant') && rows[0]?.tenant_id) setParams({ tenant: rows[0].tenant_id, ai });
      })
      .catch((reason) => live && setError(reason.message))
      .finally(() => live && setLoadingTenants(false));
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const chooseTenant = (next) => {
    setParams({ tenant: next, ai });
    setCustomer([]);
    setCopilot([]);
    setDraft('');
    setError('');
    setBusy('');
  };

  const thread = ai === 'customer' ? customer : copilot;
  const setThread = ai === 'customer' ? setCustomer : setCopilot;

  const send = async () => {
    const message = draft.trim();
    if (!tenantId || !message || busy) return;
    const startedTenant = tenantId;
    const brain = ai;
    setBusy(brain);
    setDraft('');
    const history = thread.filter((line) => line.role === 'user' || line.role === 'assistant').map((line) => ({ role: line.role, text: line.text }));
    setThread([...thread, { role: 'user', text: message }]);
    try {
      const data = await ownerApi.brainTurn(brain, {
        tenant_id: startedTenant,
        message,
        history,
        mode: brain === 'customer' && draftMode ? 'draft' : 'live',
      });
      if (tenantRef.current !== startedTenant) return;
      /** @type {BrainLine[]} */
      const extra = [];
      if (data.reply) extra.push({ role: 'assistant', text: data.reply });
      if (data.hint) extra.push({ role: 'status', text: data.hint });
      else if (!data.reply && data.reason) extra.push({ role: 'status', text: 'The AI stopped before a reply.' });
      if (data.pending_confirmation) extra.push({ role: 'status', text: `Waiting for approval: ${data.pending_confirmation}` });
      if (!extra.length) extra.push({ role: 'status', text: 'No reply yet.' });
      setThread([...thread, { role: 'user', text: message }, ...extra]);
    } catch (reason) {
      if (tenantRef.current !== startedTenant) return;
      setThread([...thread, { role: 'user', text: message }, { role: 'status', text: reason instanceof Error ? reason.message : 'Request failed' }]);
    } finally {
      if (tenantRef.current === startedTenant) setBusy('');
    }
  };

  const title = ai === 'customer' ? 'Customer AI' : 'Owner Copilot';
  return (
    <div className="max-w-[880px] space-y-4">
      <PageHeader title="Test the AI" subtitle="Chat with a business's AI as a customer or as the owner. Tests don't use their messages." />
      <label className="block text-sm text-slate-700">Business
        <select aria-label="Business" value={tenantId} onChange={(event) => chooseTenant(event.target.value)} className="mt-1 h-11 w-full rounded-lg border border-[#7C8798] bg-white px-3">
          {loadingTenants ? <option value="">Loading businesses…</option> : null}
          {subscribers.map((row) => <option key={row.tenant_id} value={row.tenant_id}>{row.business_name || row.email || row.tenant_id}</option>)}
        </select>
      </label>
      <div role="tablist" className="flex gap-2">
        <button type="button" role="tab" aria-selected={ai === 'customer'} className={ai === 'customer' ? 'border-b-2 border-[#0F766E] bg-[#F0FDFA] px-3 py-2 text-sm text-[#0F766E]' : 'px-3 py-2 text-sm text-slate-700'} onClick={() => setParams({ tenant: tenantId, ai: 'customer' })}>Customer AI</button>
        <button type="button" role="tab" aria-selected={ai === 'copilot'} className={ai === 'copilot' ? 'border-b-2 border-[#0F766E] bg-[#F0FDFA] px-3 py-2 text-sm text-[#0F766E]' : 'px-3 py-2 text-sm text-slate-700'} onClick={() => setParams({ tenant: tenantId, ai: 'copilot' })}>Owner Copilot</button>
      </div>
      {ai === 'customer' ? (
        <>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={draftMode} onChange={(event) => setDraftMode(event.target.checked)} /> Use unpublished changes</label>
          <p className="text-[13px] text-slate-600">Try your latest edits before customers see them.</p>
        </>
      ) : null}
      {error ? <p role="alert" className="text-sm text-red-800">{error}</p> : null}
      <section className="rounded-xl border border-slate-200 bg-white p-4">
        {thread.length === 0 ? (
          <EmptyState
            icon={ai === 'customer' ? <UserIcon className="h-6 w-6" /> : <SparklesIcon className="h-6 w-6" />}
            title={ai === 'customer' ? 'Write like a customer would' : 'Ask like the business owner would'}
            text={ai === 'customer' ? 'For example: What are your prices?' : 'For example: How many messages did I get this week?'}
          />
        ) : thread.map((line, index) => (
          <p key={`${line.role}-${index}`} className={line.role === 'user' ? 'ml-8 mt-2 rounded-lg bg-teal-50 p-3 text-sm' : 'mr-8 mt-2 rounded-lg border p-3 text-sm'}>
            {line.role === 'assistant' ? <span dangerouslySetInnerHTML={replyHtml(line.text)} /> : line.text}
            {line.role === 'status' ? <TechDetails text={line.text} /> : null}
          </p>
        ))}
        <form className="mt-4 flex gap-2" onSubmit={(event) => { event.preventDefault(); void send(); }}>
          <textarea aria-label={`Message ${title}`} value={draft} onChange={(event) => setDraft(event.target.value)} className="min-h-11 flex-1 rounded-lg border border-[#7C8798] px-3 py-2 text-sm" placeholder="Type a message…" />
          <Button type="submit" aria-label={`Send to ${title}`} quietDisabled className={(!tenantId || !!busy || !draft.trim()) ? 'bg-slate-200 text-slate-600' : ''} disabled={!tenantId || !!busy || !draft.trim()}>{busy ? 'Sending…' : 'Send'}</Button>
        </form>
        {!tenantId ? <p className="mt-2 text-sm text-slate-600">Choose a business first</p> : !draft.trim() ? <p className="mt-2 text-sm text-slate-600">Type a message to send</p> : null}
      </section>
    </div>
  );
}
