// @ts-nocheck
import { useState } from 'react';
import { ownerApi } from './ownerApi';
import { useLoad } from './lib/useLoad';
import { label } from './lib/labels';
import { businessDisplayName, formatDateTime, formatRelative } from './lib/format';
import PageHeader from './ui/PageHeader';
import DataTable from './ui/DataTable';
import TechDetails from './ui/TechDetails';
import EmptyState from './ui/EmptyState';
import Alert from './ui/Alert';
import { ClipboardDocumentListIcon } from '@heroicons/react/24/outline';

export default function OwnerAudit() {
  const state = useLoad(() => ownerApi.audit().then((data) => data.events || []), []);
  const [showTests, setShowTests] = useState(false);
  const [selected, setSelected] = useState(null);
  const rows = (state.data || []).filter((row) => showTests || !String(row.reason || row.action || '').toLowerCase().includes('brain'));
  return (
    <div className="space-y-6">
      <PageHeader title="Activity log" subtitle="Changes and actions in this portal, newest first." actions={<label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={showTests} onChange={(event) => setShowTests(event.target.checked)} /> Show AI tests</label>} />
      {state.status === 'error' ? <Alert title="We couldn't load activity." detail={state.error} /> : null}
      <DataTable
        loading={state.status === 'loading'}
        columns={[
          { key: 'when', label: 'When', render: (row) => row.created_at ? <span title={formatDateTime(row.created_at)}>{formatRelative(row.created_at)}</span> : 'Time not recorded' },
          { key: 'what', label: 'What happened', render: (row) => label('auditAction', row.reason || row.action) },
          { key: 'business', label: 'Business', render: (row) => businessDisplayName(row) || 'Unknown business' },
        ]}
        rows={rows}
        onRowClick={(row) => setSelected(row)}
        getRowId={(row) => row.id || `${row.action}-${row.created_at}`}
        searchText={(row) => `${row.action} ${row.tenant_id}`}
        empty={<EmptyState icon={<ClipboardDocumentListIcon className="h-6 w-6" />} title="No activity yet" text="Price changes and account actions will show up here." />}
      />
      {selected ? (
        <div className="rounded-xl border border-slate-200 bg-white p-4">
          <h2 className="text-base font-semibold">{label('auditAction', selected.reason || selected.action)}</h2>
          <p className="mt-2 text-sm">{businessDisplayName(selected) || 'Unknown business'}</p>
          <p className="text-sm">{selected.created_at ? formatRelative(selected.created_at) : 'Time not recorded'}</p>
          <button type="button" className="mt-3 text-sm text-teal-800" onClick={() => setSelected(null)}>Close</button>
          <TechDetails text="More fields are hidden from the main list." />
        </div>
      ) : null}
    </div>
  );
}
