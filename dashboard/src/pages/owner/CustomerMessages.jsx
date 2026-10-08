// @ts-nocheck
import { useState } from 'react';
import { Link, useLocation, useSearchParams } from 'react-router-dom';
import { ownerApi } from './ownerApi';
import { useLoad } from './lib/useLoad';
import { label } from './lib/labels';
import { formatDateTime, formatRelative } from './lib/format';
import { statusLabel, statusTone } from './lib/status';
import { replyHtml } from './replyFormat';
import PageHeader from './ui/PageHeader';
import Badge from './ui/Badge';
import Button from './ui/Button';
import TechDetails from './ui/TechDetails';
import EmptyState from './ui/EmptyState';
import Alert from './ui/Alert';
import { SkeletonRows } from './ui/Skeleton';
import { ChatBubbleLeftRightIcon } from '@heroicons/react/24/outline';

export default function CustomerMessages() {
  const location = useLocation();
  const tab = location.pathname.includes('/traces') ? 'traces' : 'messages';
  const [params, setParams] = useSearchParams();
  const tenant = params.get('tenant') || '';
  const flows = useLoad(() => ownerApi.messageFlows({ tenant_id: tenant, limit: 80 }).then((data) => data.messages || []), [tenant, tab]);
  const traces = useLoad(() => ownerApi.listTraces({ tenant_id: tenant, brain: params.get('brain') || '' }).then((data) => data.traces || []), [tenant, params.get('brain'), tab]);
  const [selected, setSelected] = useState(/** @type {any} */ (null));
  const businesses = useLoad(() => ownerApi.subscribers().then((data) => data.subscribers || []), []);

  return (
    <div className="space-y-4">
      <PageHeader
        title="Customer messages"
        subtitle="Every customer message the AI handled, and how it replied."
        actions={(
          <select aria-label="Business" value={tenant} onChange={(event) => setParams(event.target.value ? { tenant: event.target.value } : {})} className="h-9 rounded-lg border border-[#7C8798] bg-white px-3 text-sm">
            <option value="">All businesses</option>
            {(businesses.data || []).filter((row) => !row.hide_by_default).map((row) => <option key={row.tenant_id} value={row.tenant_id}>{row.business_name || row.tenant_id}</option>)}
          </select>
        )}
      />
      <div role="tablist" aria-label="Customer message views" className="flex gap-2">
        <Link role="tab" aria-selected={tab === 'messages'} to={tenant ? `/owner/messages?tenant=${tenant}` : '/owner/messages'} className={`rounded-lg px-3 py-2 text-sm ${tab === 'messages' ? 'bg-[#F0FDFA] text-[#0F766E]' : 'text-slate-700'}`}>Messages</Link>
        <Link role="tab" aria-selected={tab === 'traces'} to={tenant ? `/owner/traces?tenant=${tenant}` : '/owner/traces'} className={`rounded-lg px-3 py-2 text-sm ${tab === 'traces' ? 'bg-[#F0FDFA] text-[#0F766E]' : 'text-slate-700'}`}>AI traces</Link>
      </div>
      {tab === 'traces' ? <p className="text-[13px] text-slate-600">Step-by-step record of each AI answer, including test chats.</p> : null}
      {tab === 'messages' ? (
        <div className="grid gap-4 lg:grid-cols-12">
          <div className="lg:col-span-5">
            {flows.status === 'loading' ? <SkeletonRows /> : null}
            {flows.status === 'error' ? <Alert title="We couldn't load messages." detail={flows.error} /> : null}
            {flows.status === 'ready' && flows.data.length === 0 ? <EmptyState icon={<ChatBubbleLeftRightIcon className="h-6 w-6" />} title={tenant ? 'No messages for this business' : 'No customer messages yet'} text="Messages appear here when customers write to a connected business." /> : null}
            <ul className="space-y-2">
              {(flows.status === 'ready' ? flows.data : []).map((row) => (
                <li key={row.operation_id || row.updated_at}>
                  <button type="button" onClick={() => setSelected(row)} className="w-full rounded-lg border border-slate-200 bg-white p-3 text-left">
                    <span className="flex justify-between text-sm"><span>{label('channel', row.channel)}</span><Badge tone={statusTone('message', row.state)}>{statusLabel('message', row.state)}</Badge></span>
                    <span className="mt-1 block truncate text-sm" dir="auto">{row.inbound_preview || '—'}</span>
                    <span className="mt-1 block text-[13px] text-slate-600" title={formatDateTime(row.updated_at)}>{formatRelative(row.updated_at)}</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
          <div className="lg:sticky lg:top-20 lg:col-span-7 lg:max-h-[calc(100vh-96px)] lg:overflow-y-auto">
            {!selected ? <EmptyState icon={<ChatBubbleLeftRightIcon className="h-6 w-6" />} title="Select a message" text="Select a message to see the conversation." /> : (
              <div className="rounded-xl border border-slate-200 bg-white p-5">
                <Badge tone={statusTone('message', selected.state)}>{statusLabel('message', selected.state)}</Badge>
                <p className="mt-3 rounded-lg bg-slate-100 p-3 text-sm" dir="auto">{selected.inbound_preview}</p>
                {(selected.reply_messages || []).map((reply, index) => <p key={index} className="mt-3 rounded-lg border p-3 text-sm" dangerouslySetInnerHTML={replyHtml(reply.text || '')} />)}
                <p className="mt-3 text-sm text-slate-700">Reply type: {label('responseClass', selected.response_class || 'generated_ai')}</p>
                <TechDetails text={JSON.stringify(selected, null, 2)} />
              </div>
            )}
          </div>
        </div>
      ) : (
        <div>
          <label className="mb-3 flex items-center gap-2 text-sm">AI
            <select aria-label="AI" value={params.get('brain') || ''} onChange={(event) => { const next = new URLSearchParams(params); if (event.target.value) next.set('brain', event.target.value); else next.delete('brain'); setParams(next); }} className="h-9 rounded-lg border border-[#7C8798] px-3">
              <option value="">All</option>
              <option value="customer">Customer AI</option>
              <option value="owner_copilot">Owner Copilot</option>
            </select>
          </label>
          {traces.status === 'loading' ? <SkeletonRows /> : null}
          {traces.status === 'ready' && traces.data.length === 0 ? <EmptyState icon={<ChatBubbleLeftRightIcon className="h-6 w-6" />} title="No AI traces yet" text="Send a test message to see how the AI answers." action={<Link to="/owner/brains"><Button variant="secondary">Open Test the AI</Button></Link>} /> : null}
          <ul className="space-y-2">
            {(traces.status === 'ready' ? traces.data : []).map((row) => (
              <li key={row.id} className="rounded-lg border border-slate-200 bg-white p-3 text-sm">
                <span className="font-medium">{label('brain', row.brain)}</span>
                {row.channel === 'brains_test' ? <Badge tone="info">Test chat</Badge> : null}
                <Badge tone={statusTone('trace', row.has_error)}>{statusLabel('trace', row.has_error)}</Badge>
                <p className="mt-1" dir="auto">{row.payload?.user_message || '—'}</p>
                <p className="text-[13px] text-slate-600" title={formatDateTime(row.created_at)}>{formatRelative(row.created_at)}</p>
                <TechDetails text={JSON.stringify(row.payload || {}, null, 2)} />
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
