// @ts-nocheck
import { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ownerApi } from './ownerApi';
import { useLoad } from './lib/useLoad';
import { formatNumber } from './lib/format';
import { label } from './lib/labels';
import { statusLabel, statusTone } from './lib/status';
import PageHeader from './ui/PageHeader';
import DataTable from './ui/DataTable';
import Badge from './ui/Badge';
import Button from './ui/Button';
import ConfirmDialog from './ui/ConfirmDialog';
import Alert from './ui/Alert';
import EmptyState from './ui/EmptyState';
import { BuildingStorefrontIcon } from '@heroicons/react/24/outline';

export default function OwnerTenants() {
  const [params, setParams] = useSearchParams();
  const [query, setQuery] = useState('');
  const [sort, setSort] = useState('name');
  const [hideTest, setHideTest] = useState(true);
  const [pending, setPending] = useState(/** @type {any} */ (null));
  const [notice, setNotice] = useState('');
  const state = useLoad(() => ownerApi.subscribers().then((data) => data.subscribers || []), []);
  const openId = params.get('open') || '';
  const visible = useMemo(() => {
    const rows = (state.data || []).filter((row) => !(hideTest && row.hide_by_default));
    const needle = query.trim().toLowerCase();
    const filtered = rows.filter((row) => `${row.business_name || ''} ${row.email || ''} ${row.tenant_id || ''}`.toLowerCase().includes(needle));
    filtered.sort((left, right) => {
      if (sort === 'messages') return Number(right.messages_remaining || 0) - Number(left.messages_remaining || 0);
      const a = sort === 'tenant' ? left.tenant_id : (left.business_name || left.email || '');
      const b = sort === 'tenant' ? right.tenant_id : (right.business_name || right.email || '');
      return String(a).localeCompare(String(b));
    });
    return filtered;
  }, [state.data, query, sort, hideTest]);
  const selected = (state.data || []).find((row) => row.tenant_id === openId);

  const exportCsv = () => {
    const header = 'tenant_id,business_name,email,membership,messages_remaining';
    const lines = visible.map((row) => [row.tenant_id, row.business_name, row.email, row.membership, row.messages_remaining]
      .map((value) => `"${String(value ?? '').replaceAll('"', '""')}"`).join(','));
    const blob = new Blob([[header, ...lines].join('\n')], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'tenants.csv';
    link.click();
    URL.revokeObjectURL(url);
  };

  const hide = async (row) => {
    const owner = (row.users || []).find((user) => user.role === 'owner') || row.users?.[0];
    if (!owner?.id) return;
    await ownerApi.updateUser(owner.id, { status: 'blocked' });
    setNotice(`${row.business_name || row.tenant_id} is hidden.`);
    setPending(null);
  };

  return (
    <div className="space-y-6">
      <PageHeader title="Businesses" subtitle="Every business using Linas AI. Click one to see details." actions={<Button variant="secondary" onClick={exportCsv}>Export CSV</Button>} />
      {notice ? <p className="text-sm text-green-800">{notice}</p> : null}
      {state.status === 'error' ? <Alert title="We couldn't load businesses." detail={state.error} /> : null}
      <div className="flex flex-wrap gap-3">
        <input aria-label="Search by name, email or ID" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search by name, email or ID" className="h-9 rounded-lg border border-[#7C8798] px-3 text-sm" />
        <select aria-label="Sort" value={sort} onChange={(event) => setSort(event.target.value)} className="h-9 rounded-lg border border-[#7C8798] px-3 text-sm">
          <option value="name">Name A–Z</option>
          <option value="tenant">ID A–Z</option>
          <option value="messages">Most messages left</option>
        </select>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={!hideTest} onChange={(event) => setHideTest(!event.target.checked)} /> Show test & blocked accounts</label>
      </div>
      <DataTable
        loading={state.status === 'loading'}
        columns={[
          { key: 'name', label: 'Business', render: (row) => <span className="font-semibold">{row.business_name || row.email || row.tenant_id}</span> },
          { key: 'plan', label: 'Plan', render: (row) => <Badge tone="neutral">{label('plan', row.subscription || 'none')}</Badge> },
          { key: 'sub', label: 'Subscription', render: (row) => <Badge tone={statusTone('user', row.membership === 'active' ? 'active' : 'none')}>{label('membership', row.membership || 'none')}</Badge> },
          { key: 'messages', label: 'Messages left', align: 'right', render: (row) => formatNumber(row.messages_remaining) },
          { key: 'status', label: 'Status', render: (row) => <Badge tone={statusTone('user', row.hide_by_default ? 'test' : 'active')}>{statusLabel('user', row.hide_by_default ? 'test' : 'active')}</Badge> },
          { key: 'hide', label: '', render: (row) => <Button variant="tertiary" onClick={() => setPending(row)}>Hide business</Button> },
        ]}
        rows={visible}
        getRowId={(row) => row.tenant_id}
        searchText={(row) => `${row.business_name} ${row.email} ${row.tenant_id}`}
        onRowClick={(row) => setParams({ open: row.tenant_id })}
        empty={state.status === 'ready' ? <EmptyState icon={<BuildingStorefrontIcon className="h-6 w-6" />} title={query ? `No businesses match "${query}"` : 'No businesses yet'} text={query ? 'Try a different search.' : 'Businesses appear here when they sign up in the app.'} /> : null}
      />
      {selected ? (
        <div className="fixed inset-0 z-40 flex justify-end bg-slate-900/40">
          <aside className="h-full w-full max-w-[560px] overflow-y-auto bg-white p-5">
            <h2 className="text-base font-semibold">{selected.business_name || selected.tenant_id}</h2>
            <p className="text-sm text-slate-600">{selected.tenant_id}</p>
            <p className="mt-4 text-sm">{formatNumber(selected.messages_remaining)} messages left</p>
            <p className="text-sm">{formatNumber(selected.historical_credit_remaining)} old credits left</p>
            <div className="mt-4"><Button variant="tertiary" onClick={() => setPending(selected)}>Hide business</Button></div>
            <button type="button" className="mt-6 text-sm text-[#0F766E]" onClick={() => setParams({})}>Close</button>
          </aside>
        </div>
      ) : null}
      {pending ? (
        <ConfirmDialog
          title={`Hide ${pending.business_name || pending.tenant_id}?`}
          body="This blocks the owner's sign-in and hides the business from lists. No data is deleted. You can unblock the owner later from Users."
          confirmLabel="Hide business"
          onClose={() => setPending(null)}
          onConfirm={() => hide(pending)}
        />
      ) : null}
    </div>
  );
}
