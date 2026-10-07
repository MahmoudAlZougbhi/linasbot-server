import { useEffect, useState } from 'react';
import { ownerApi } from './ownerApi';
import OwnerActivationBanner from './OwnerActivationBanner';

const ranges = [
  ['last_day', 'Last day'],
  ['last_7_days', 'Last 7 days'],
  ['last_week', 'Last week'],
  ['last_month', 'Last month'],
  ['last_6_months', 'Last 6 months'],
  ['last_year', 'Last year'],
];

/** @param {{ label: string; value?: number }} props */
function Metric({ label, value }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
      <p className="text-sm text-slate-400">{label}</p>
      <p className="mt-2 text-2xl font-semibold">{Number(value || 0).toLocaleString()}</p>
    </div>
  );
}

export default function OwnerOverview() {
  const [range, setRange] = useState('last_7_days');
  const [analytics, setAnalytics] = useState(/** @type {OwnerAnalytics | null} */ (null));
  const [error, setError] = useState('');

  useEffect(() => {
    let live = true;
    setError('');
    ownerApi.analytics(range)
      .then((data) => live && setAnalytics(data.analytics))
      .catch((reason) => live && setError(reason.message));
    return () => { live = false; };
  }, [range]);

  const channels = analytics?.messages_by_channel || {};
  return (
    <div className="space-y-7">
      <OwnerActivationBanner />
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-2xl font-semibold">Business overview</h2>
          <p className="mt-1 text-sm text-slate-400">Real platform sources only. Coverage notes are shown below.</p>
        </div>
        <select
          value={range}
          onChange={(event) => setRange(event.target.value)}
          className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm"
        >
          {ranges.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </header>
      {error && <p role="alert" className="rounded-lg bg-red-950 p-3 text-sm text-red-200">{error}</p>}
      {!error && !analytics ? <p className="text-sm text-slate-400">Loading overview…</p> : null}
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Metric label="New users" value={analytics?.new_users} />
        <Metric label="Live users" value={analytics?.live_users} />
        <Metric label="Subscribers" value={analytics?.subscribers} />
        <Metric label="Comments captured" value={analytics?.comments} />
        <Metric label="Intended message MRR" value={analytics?.intended_message_mrr_usd} />
        <Metric label="Live checkout MRR" value={analytics?.live_checkout_mrr_usd} />
        <Metric label="Legacy credits total" value={analytics?.credits_total} />
        <Metric label="Legacy credits used" value={analytics?.credits_used} />
        <Metric label="Legacy credits remaining" value={analytics?.credits_remaining} />
      </section>
      <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
        <h3 className="font-semibold">Messages by channel</h3>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {['facebook', 'instagram', 'tiktok', 'whatsapp', 'web', 'unknown'].map((channel) => {
            const count = Number(channels[channel] || 0);
            const max = Math.max(1, ...Object.values(channels).map((value) => Number(value) || 0));
            return (
              <div key={channel} className="rounded-lg bg-slate-950 p-3">
                <p className="capitalize text-slate-400">{channel.replace('_', ' ')}</p>
                <p className="mt-1 text-xl font-semibold">{count.toLocaleString()}</p>
                <div className="mt-2 h-1.5 rounded bg-slate-800">
                  <div className="h-1.5 rounded bg-teal-500" style={{ width: `${Math.round((count / max) * 100)}%` }} />
                </div>
              </div>
            );
          })}
        </div>
      </section>
      <section className="rounded-xl border border-amber-900/60 bg-amber-950/30 p-5 text-sm text-amber-100">
        <h3 className="font-semibold">Data coverage</h3>
        <ul className="mt-2 list-disc space-y-1 pl-5">
          {Object.entries(analytics?.coverage || {}).map(([key, value]) => (
            <li key={key}><span className="font-medium capitalize">{key}:</span> {String(value)}</li>
          ))}
        </ul>
      </section>
    </div>
  );
}
