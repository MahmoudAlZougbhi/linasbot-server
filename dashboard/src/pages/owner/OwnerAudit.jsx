// @ts-nocheck
import { ownerApi } from './ownerApi';
import { useLoad } from './lib/useLoad';
import { label } from './lib/labels';
import { formatDateTime, formatRelative } from './lib/format';
import PageHeader from './ui/PageHeader';
import DataTable from './ui/DataTable';
import TechDetails from './ui/TechDetails';
import EmptyState from './ui/EmptyState';
import Alert from './ui/Alert';
import { ClipboardDocumentListIcon } from '@heroicons/react/24/outline';

export default function OwnerAudit() {
  const state = useLoad(() => ownerApi.audit().then((data) => data.events || []), []);
  return (
    <div className="space-y-6">
      <PageHeader title="Activity log" subtitle="Changes and actions in this portal, newest first." />
      {state.status === 'error' ? <Alert title="We couldn't load activity." detail={state.error} /> : null}
      <DataTable
        loading={state.status === 'loading'}
        columns={[
          { key: 'when', label: 'When', render: (row) => row.created_at ? <span title={formatDateTime(row.created_at)}>{formatRelative(row.created_at)}</span> : 'Time not recorded' },
          { key: 'what', label: 'What happened', render: (row) => label('auditAction', row.reason || row.action) },
          { key: 'business', label: 'Business', render: (row) => row.tenant_id || '—' },
          { key: 'by', label: 'By', render: () => 'Platform owner' },
          { key: 'raw', label: '', render: (row) => <TechDetails text={JSON.stringify(row)} /> },
        ]}
        rows={state.data || []}
        getRowId={(row) => row.id || `${row.action}-${row.created_at}`}
        searchText={(row) => `${row.action} ${row.tenant_id}`}
        empty={<EmptyState icon={<ClipboardDocumentListIcon className="h-6 w-6" />} title="No activity yet" text="Price changes, AI tests and account actions will show up here." />}
      />
    </div>
  );
}
