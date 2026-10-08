// @ts-nocheck
import { useState } from 'react';
import { ownerApi } from './ownerApi';
import { useLoad } from './lib/useLoad';
import { formatNumber, formatUsd } from './lib/format';
import { MAPS, READINESS, label } from './lib/labels';
import PageHeader from './ui/PageHeader';
import Card from './ui/Card';
import Button from './ui/Button';
import Alert from './ui/Alert';
import TechDetails from './ui/TechDetails';
import { SkeletonRows } from './ui/Skeleton';
import EmptyState from './ui/EmptyState';
import { ChatBubbleLeftRightIcon } from '@heroicons/react/24/outline';

const ranges = ['last_day', 'last_7_days', 'last_month', 'last_6_months', 'last_year', 'last_week'];

export default function OwnerOverview() {
  const [range, setRange] = useState('last_7_days');
  const [open, setOpen] = useState(false);
  const state = useLoad(() => ownerApi.analytics(range).then((data) => data.analytics), [range]);
  const ready = useLoad(() => ownerApi.activationReadiness().then((data) => data.readiness), []);
  const analytics = state.data;
  const channels = analytics?.messages_by_channel || {};
  const positive = Object.entries(channels).filter(([, count]) => Number(count) > 0).sort((a, b) => Number(b[1]) - Number(a[1]));
  const total = positive.reduce((sum, [, count]) => sum + Number(count), 0);
  const blockers = ready.data?.blockers || ready.data?.items || [];
  const blockerCount = Array.isArray(blockers) ? blockers.length : 0;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Overview"
        subtitle="How your business is doing at a glance."
        actions={(
          <select aria-label="Period" value={range} onChange={(event) => setRange(event.target.value)} className="h-9 rounded-lg border border-[#7C8798] bg-white px-3 text-sm">
            {ranges.map((value) => <option key={value} value={value}>{label('range', value)}</option>)}
          </select>
        )}
      />
      {ready.status === 'error' ? <p className="text-sm text-slate-600">Launch status isn&apos;t available right now. <button type="button" className="text-[#0F766E]" onClick={() => window.location.reload()}>Try again</button></p> : null}
      {ready.status === 'ready' && blockerCount > 0 ? (
        <Card className="border-l-4 border-l-amber-300">
          <h2 className="text-base font-semibold">Message plans aren&apos;t live yet</h2>
          <p className="mt-1 text-sm text-slate-700">{blockerCount} setup items are still open. Customers keep using the current credit plans until these are done.</p>
          <div className="mt-3"><Button variant="secondary" onClick={() => setOpen(true)}>View checklist</Button></div>
        </Card>
      ) : null}
      {ready.status === 'ready' && blockerCount === 0 ? <Card><p className="text-sm font-semibold text-green-800">Message plans are live</p></Card> : null}
      {state.status === 'error' ? <Alert title="We couldn't load the overview." detail={state.error} onRetry={() => setRange((value) => value)} /> : null}
      {state.status === 'loading' ? <SkeletonRows rows={4} /> : null}
      {state.status === 'ready' ? (
        <>
          <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <Card><p className="text-sm font-medium text-slate-600">New users</p><p className="mt-2 text-3xl font-semibold tabular-nums">{formatNumber(analytics.new_users)}</p><p className="text-sm text-slate-600">In the selected period</p></Card>
            <Card><p className="text-sm font-medium text-slate-600">Active users</p><p className="mt-2 text-3xl font-semibold tabular-nums">{formatNumber(analytics.live_users)}</p></Card>
            <Card><p className="text-sm font-medium text-slate-600">Paying subscribers</p><p className="mt-2 text-3xl font-semibold tabular-nums">{formatNumber(analytics.subscribers)}</p></Card>
            <Card><p className="text-sm font-medium text-slate-600">Comments received</p><p className="mt-2 text-3xl font-semibold tabular-nums">{formatNumber(analytics.comments)}</p></Card>
          </section>
          <section className="grid gap-4 lg:grid-cols-2">
            <Card title="Monthly recurring revenue (USD)">
              <p className="text-3xl font-semibold tabular-nums">{formatUsd(analytics.live_checkout_mrr_usd)}</p>
              <p className="text-sm text-slate-600">What subscribers pay today</p>
            </Card>
            <Card title="Messages left (all businesses)">
              <p className="text-3xl font-semibold tabular-nums">{formatNumber(analytics.messages_remaining ?? analytics.credits_remaining)}</p>
            </Card>
          </section>
          <Card title="Messages by channel" action={<span className="text-sm text-slate-600">{formatNumber(total)} messages</span>}>
            {total === 0 ? (
              <EmptyState icon={<ChatBubbleLeftRightIcon className="h-6 w-6" />} title="No messages in this period" text="Try a longer period." action={<Button variant="secondary" onClick={() => setRange('last_month')}>Show last 30 days</Button>} />
            ) : positive.map(([channel, count]) => (
              <div key={channel} className="mt-3">
                <div className="flex justify-between text-sm"><span>{MAPS.channel[channel] || label('channel', channel)}</span><span className="tabular-nums">{formatNumber(count)}</span></div>
                <div className="mt-1 h-2 rounded bg-slate-100"><div className="h-2 rounded bg-[#0F766E]" style={{ width: `${Math.round((Number(count) / total) * 100)}%` }} /></div>
              </div>
            ))}
          </Card>
        </>
      ) : null}
      {open ? (
        <div className="fixed inset-0 z-50 flex justify-end bg-slate-900/40">
          <div className="h-full w-full max-w-[560px] overflow-y-auto bg-white p-5">
            <div className="flex justify-between"><h2 className="text-base font-semibold">Launch checklist</h2><button type="button" onClick={() => setOpen(false)}>Close</button></div>
            {Array.isArray(blockers) ? blockers.map((key) => {
              const item = READINESS[key] || { label: label('auditAction', key), text: '', group: 'Other' };
              return <p key={key} className="mt-3 text-sm"><span className="font-semibold">{item.label}.</span> {item.text}</p>;
            }) : null}
            <TechDetails text={JSON.stringify(blockers)} />
          </div>
        </div>
      ) : null}
    </div>
  );
}
