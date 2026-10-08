// @ts-nocheck
import { useEffect, useState } from 'react';
import { Link, useLocation, useSearchParams } from 'react-router-dom';
import { ownerApi } from './ownerApi';
import { useLoad } from './lib/useLoad';
import { label } from './lib/labels';
import { businessDisplayName, formatDateTime, formatRelative } from './lib/format';
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

function phaseReason(phase) {
  const key = String(phase || '');
  if (!key) return 'No reason was recorded.';
  if (key === 'generate') return 'Failed while writing the reply.';
  return `Failed during ${label('traceStep', key) === 'Not set' ? key.replaceAll('_', ' ') : label('traceStep', key)}.`;
}

export default function CustomerMessages() {
  const location = useLocation();
  const traces = location.pathname.includes('/traces');
  const [params, setParams] = useSearchParams();
  const tenant = params.get('tenant') || '';
  const [showTests, setShowTests] = useState(false);
  const flows = useLoad(() => ownerApi.messageFlows({ tenant_id: tenant, limit: 80 }).then((data) => data.messages || []), [tenant]);
  const traceRows = useLoad(() => ownerApi.listTraces({ tenant_id: tenant, brain: params.get('brain') || '' }).then((data) => data.traces || []), [tenant, params.get('brain'), traces]);
  const businesses = useLoad(() => ownerApi.subscribers().then((data) => data.subscribers || []), []);
  const [selected, setSelected] = useState(/** @type {any} */ (null));
  const [detail, setDetail] = useState(/** @type {any} */ (null));
  const named = (id) => businessDisplayName((businesses.data || []).find((row) => row.tenant_id === id) || { tenant_id: id });

  useEffect(() => {
    if (traces) {
      const id = params.get('id');
      const row = (traceRows.data || []).find((item) => item.id === id);
      if (row) setSelected(row);
    }
  }, [traces, params, traceRows.data]);

  useEffect(() => {
    if (traces || !selected?.tenant_id || !selected?.operation_id) {
      setDetail(selected);
      return undefined;
    }
    let live = true;
    ownerApi.messageFlow(selected.tenant_id, selected.operation_id).then((data) => {
      if (live) setDetail(data.message || data.flow || data);
    }).catch(() => { if (live) setDetail(selected); });
    return () => { live = false; };
  }, [selected, traces]);

  const messageRows = (flows.data || []).filter((row) => showTests || (row.channel !== 'brains_test' && row.source !== 'lab'));

  return (
    <div className="space-y-4">
      <PageHeader
        title={traces ? 'AI traces' : 'Customer messages'}
        subtitle={traces ? 'Step-by-step record of each AI answer, including test chats.' : 'Every customer message the AI handled, and how it replied.'}
        actions={(
          <select aria-label="Business" value={tenant} onChange={(event) => setParams(event.target.value ? { tenant: event.target.value } : {})} className="h-9 rounded-lg border border-[#7C8798] bg-white px-3 text-sm">
            <option value="">All businesses</option>
            {(businesses.data || []).filter((row) => !row.hide_by_default).map((row) => <option key={row.tenant_id} value={row.tenant_id}>{businessDisplayName(row)}</option>)}
          </select>
        )}
      />
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={showTests} onChange={(event) => setShowTests(event.target.checked)} /> Show test chats</label>
      {traces ? (
        <div className="grid gap-4 lg:grid-cols-12">
          <div className="lg:col-span-5">
            <label className="mb-3 flex items-center gap-2 text-sm">Which AI
              <select aria-label="Which AI" value={params.get('brain') || ''} onChange={(event) => { const next = new URLSearchParams(params); if (event.target.value) next.set('brain', event.target.value); else next.delete('brain'); setParams(next); }} className="h-9 rounded-lg border border-[#7C8798] bg-white px-3">
                <option value="">All</option>
                <option value="customer">Customer AI</option>
                <option value="owner_copilot">Owner Copilot</option>
              </select>
            </label>
            {traceRows.status === 'loading' ? <SkeletonRows /> : null}
            {traceRows.status === 'ready' && traceRows.data.length === 0 ? <EmptyState icon={<ChatBubbleLeftRightIcon className="h-6 w-6" />} title="No AI traces yet" text="Send a test message to see how the AI answers." action={<Link to="/owner/brains"><Button variant="secondary">Open Test the AI</Button></Link>} /> : null}
            <ul className="space-y-2">
              {(traceRows.status === 'ready' ? traceRows.data : []).map((row) => (
                <li key={row.id}>
                  <button type="button" aria-current={selected?.id === row.id ? 'true' : undefined} onClick={() => setSelected(row)} className={`w-full rounded-lg border p-3 text-left text-sm ${selected?.id === row.id ? 'border-teal-600 bg-teal-50' : 'border-slate-200 bg-white'}`}>
                    <span className="font-medium">{label('brain', row.brain)}</span>
                    {row.channel === 'brains_test' ? <Badge tone="info">Test chat</Badge> : null}
                    <Badge tone={statusTone('trace', row.has_error)}>{statusLabel('trace', row.has_error)}</Badge>
                    <p className="mt-1" dir="auto">{row.payload?.user_message || '—'}</p>
                    <p className="text-[13px] text-slate-600" title={formatDateTime(row.created_at)}>{formatRelative(row.created_at)}</p>
                  </button>
                </li>
              ))}
            </ul>
          </div>
          <div className="lg:col-span-7">
            {selected ? (
              <div className="rounded-xl border border-slate-200 bg-white p-5 text-sm">
                <p dir="auto">{selected.payload?.user_message}</p>
                <p className="mt-3" dir="auto" dangerouslySetInnerHTML={replyHtml(selected.payload?.reply || '')} />
                <TechDetails text={JSON.stringify(selected.payload || {}, null, 2)} />
              </div>
            ) : <EmptyState icon={<ChatBubbleLeftRightIcon className="h-6 w-6" />} title="Select a trace" text="Choose a row to see the record." />}
          </div>
        </div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-12">
          <div className="lg:col-span-5">
            {flows.status === 'loading' ? <SkeletonRows /> : null}
            {flows.status === 'error' ? <Alert title="We couldn't load messages." detail={flows.error} /> : null}
            {flows.status === 'ready' && messageRows.length === 0 ? <EmptyState icon={<ChatBubbleLeftRightIcon className="h-6 w-6" />} title={tenant ? 'No messages for this business' : 'No customer messages yet'} text="Messages appear here when customers write to a connected business." /> : null}
            <ul className="space-y-2">
              {messageRows.map((row) => {
                const status = row.state ? statusLabel('message', row.state) : '';
                const current = selected?.operation_id === row.operation_id;
                return (
                  <li key={row.operation_id || row.updated_at}>
                    <button type="button" aria-current={current ? 'true' : undefined} onClick={() => setSelected(row)} className={`w-full rounded-lg border p-3 text-left ${current ? 'border-teal-600 bg-teal-50' : 'border-slate-200 bg-white'}`}>
                      <span className="flex justify-between text-sm">
                        <span>{label('channel', row.channel)}{row.channel === 'brains_test' || row.source === 'lab' ? ' · Test chat' : ''}</span>
                        {status && status !== 'Not set' ? <Badge tone={statusTone('message', row.state)}>{status}</Badge> : null}
                      </span>
                      <span className="mt-1 block truncate text-sm" dir="auto">{row.inbound_preview || '—'}</span>
                      <span className="mt-1 block text-[13px] text-slate-600" title={formatDateTime(row.updated_at)}>{formatRelative(row.updated_at)}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
          <div className="lg:sticky lg:top-20 lg:col-span-7 lg:max-h-[calc(100vh-96px)] lg:overflow-y-auto">
            {!selected ? <EmptyState icon={<ChatBubbleLeftRightIcon className="h-6 w-6" />} title="Select a message" text="Select a message to see the conversation." /> : (
              <div className="rounded-xl border border-slate-200 bg-white p-5">
                <p className="text-sm font-semibold">{named(selected.tenant_id)}</p>
                <p className="text-sm text-slate-600">{label('channel', selected.channel)} · <span title={formatDateTime(selected.updated_at)}>{formatDateTime(selected.updated_at)}</span></p>
                {selected.state === 'failed' ? <Alert title="Why it failed" text={phaseReason(detail?.phase || selected.phase)} /> : null}
                <p className="mt-3 text-sm font-medium">Customer</p>
                <p className="mt-1 rounded-lg bg-slate-100 p-3 text-sm" dir="auto">{detail?.inbound_preview || selected.inbound_preview}</p>
                <p className="mt-3 text-sm font-medium">AI reply</p>
                <p className="mt-1 rounded-lg border p-3 text-sm" dangerouslySetInnerHTML={replyHtml(detail?.reply_preview || selected.reply_preview || '')} />
                <p className="mt-3 text-sm text-slate-700">Reply type: {label('responseClass', selected.response_class || 'generated_ai')}</p>
                <TechDetails text={JSON.stringify(detail || selected, null, 2)} />
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
