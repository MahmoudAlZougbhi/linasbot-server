// @ts-nocheck
import { useSearchParams } from 'react-router-dom';
import { ownerApi } from './ownerApi';
import { useLoad } from './lib/useLoad';
import { formatNumber, formatUsd } from './lib/format';
import { label } from './lib/labels';
import { statusLabel, statusTone } from './lib/status';
import PageHeader from './ui/PageHeader';
import Card from './ui/Card';
import Badge from './ui/Badge';
import TechDetails from './ui/TechDetails';
import Alert from './ui/Alert';
import { SkeletonRows } from './ui/Skeleton';

export default function OwnerCosts() {
  const [params, setParams] = useSearchParams();
  const tenant = params.get('tenant') || '';
  const period = params.get('period') || '';
  const filters = period ? { period } : {};
  const state = useLoad(() => (tenant ? ownerApi.tenantCosts(tenant, filters) : ownerApi.costs(filters)), [tenant, period]);
  const businesses = useLoad(() => ownerApi.subscribers().then((data) => data.subscribers || []), []);
  const data = state.data || {};
  return (
    <div className="space-y-6">
      <PageHeader
        title="AI costs"
        subtitle="What running the AI costs, per business. Prices appear once providers send invoices."
        actions={(
          <>
            <select aria-label="Business" value={tenant} onChange={(event) => setParams(event.target.value ? { tenant: event.target.value, period } : { period })} className="h-9 rounded-lg border border-[#7C8798] bg-white px-3 text-sm">
              <option value="">All businesses</option>
              {(businesses.data || []).filter((row) => !row.hide_by_default).map((row) => <option key={row.tenant_id} value={row.tenant_id}>{row.business_name || row.tenant_id}</option>)}
            </select>
            <select aria-label="Period" value={period} onChange={(event) => setParams({ ...(tenant ? { tenant } : {}), ...(event.target.value ? { period: event.target.value } : {}) })} className="h-9 rounded-lg border border-[#7C8798] bg-white px-3 text-sm">
              {['', 'today', 'yesterday', 'last_7_days', 'last_30_days'].map((value) => <option key={value || 'all'} value={value}>{label('costPeriod', value)}</option>)}
            </select>
          </>
        )}
      />
      {tenant ? <p className="text-sm text-slate-700">Showing: {(businesses.data || []).find((row) => row.tenant_id === tenant)?.business_name || tenant}</p> : null}
      {state.status === 'loading' ? <SkeletonRows rows={4} /> : null}
      {state.status === 'error' ? <Alert title="We couldn't load costs." detail={state.error} /> : null}
      {state.status === 'ready' ? (
        <>
          <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <Card><p className="text-sm text-slate-600">Confirmed cost (USD)</p><p className="text-3xl font-semibold">{formatUsd(data.known_usd)}</p></Card>
            <Card><p className="text-sm text-slate-600">Usage not priced yet</p><p className="text-3xl font-semibold">{formatNumber(data.pending_or_unpriced)}</p></Card>
            <Card><p className="text-sm text-slate-600">Messages left</p><p className="text-3xl font-semibold">{formatNumber(data.messages?.remaining)}</p></Card>
            <Card><p className="text-sm text-slate-600">Message billing</p><Badge tone={data.message_billing_on ? 'success' : 'neutral'}>{data.message_billing_on ? 'On' : 'Off'}</Badge></Card>
          </section>
          <Card title="Usage by type">
            {Object.entries(data.pending_by_category || {}).map(([key, count]) => (
              <p key={key} className="mt-2 text-sm">{label('costCategory', key)} <span className="tabular-nums">{formatNumber(count)}</span></p>
            ))}
            <Badge tone={statusTone('cost', Number(data.known_usd) > 0)}>{statusLabel('cost', Number(data.known_usd) > 0)}</Badge>
          </Card>
          <TechDetails text={data.attribution_note || ''} />
        </>
      ) : null}
    </div>
  );
}
