import { useEffect, useState } from 'react';
import { ownerApi } from './ownerApi';

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
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Metric label="New users" value={analytics?.new_users} />
        <Metric label="Live users" value={analytics?.live_users} />
        <Metric label="Subscribers" value={analytics?.subscribers} />
        <Metric label="Comments captured" value={analytics?.comments} />
        <Metric label="Credits total" value={analytics?.credits_total} />
        <Metric label="Credits used" value={analytics?.credits_used} />
        <Metric label="Credits remaining" value={analytics?.credits_remaining} />
      </section>
      <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
        <h3 className="font-semibold">Messages by channel</h3>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {['facebook', 'instagram', 'tiktok', 'whatsapp', 'web', 'testing_lab', 'unknown'].map((channel) => (
            <div key={channel} className="rounded-lg bg-slate-950 p-3">
              <p className="capitalize text-slate-400">{channel.replace('_', ' ')}</p>
              <p className="mt-1 text-xl font-semibold">{Number(channels[channel] || 0).toLocaleString()}</p>
            </div>
          ))}
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
