// @ts-nocheck
import { useSearchParams } from 'react-router-dom';
import { ownerApi } from './ownerApi';
import { useLoad } from './lib/useLoad';
import { businessDisplayName, formatNumber, formatUsd } from './lib/format';
import { label } from './lib/labels';
import PageHeader from './ui/PageHeader';
import Card from './ui/Card';
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
              {(businesses.data || []).filter((row) => !row.hide_by_default).map((row) => <option key={row.tenant_id} value={row.tenant_id}>{businessDisplayName(row)}</option>)}
            </select>
            <select aria-label="Period" value={period} onChange={(event) => setParams({ ...(tenant ? { tenant } : {}), ...(event.target.value ? { period: event.target.value } : {}) })} className="h-9 rounded-lg border border-[#7C8798] bg-white px-3 text-sm">
              {['', 'today', 'yesterday', 'last_7_days', 'last_30_days'].map((value) => <option key={value || 'all'} value={value}>{label('costPeriod', value)}</option>)}
            </select>
          </>
        )}
      />
      {tenant ? <p className="text-sm text-slate-700">Showing: {businessDisplayName((businesses.data || []).find((row) => row.tenant_id === tenant) || { tenant_id: tenant })}</p> : null}
      {state.status === 'loading' ? <SkeletonRows rows={4} /> : null}
      {state.status === 'error' ? <Alert title="We couldn't load costs." detail={state.error} /> : null}
      {state.status === 'ready' ? (
        <>
          <Card>
            <p className="text-sm text-slate-600">Confirmed cost (USD)</p>
            {data.known_usd == null ? <p className="mt-2 text-sm text-slate-700">No confirmed costs yet. Costs appear once AI providers&apos; prices are connected.</p> : <p className="text-3xl font-semibold">{formatUsd(data.known_usd)}</p>}
          </Card>
          <Card title="Usage this period">
            {Object.entries(data.pending_by_category || {}).map(([key, count]) => (
              <p key={key} className="mt-2 text-sm">{label('costCategory', key)} <span className="tabular-nums">{formatNumber(count)}</span></p>
            ))}
          </Card>
          <details>
            <summary className="text-sm text-slate-600">Advanced</summary>
            <TechDetails text={`${data.attribution_note || ''}\n${JSON.stringify(data.usage_classes?.by_class || {})}\n${JSON.stringify(data.daily_edits?.tenants || [])}`} />
          </details>
        </>
      ) : null}
    </div>
  );
}
