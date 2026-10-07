import { useEffect, useMemo, useState } from 'react';
import { ownerApi } from './ownerApi';

export default function OwnerTenants() {
  const [rows, setRows] = useState(/** @type {any[]} */ ([]));
  const [query, setQuery] = useState('');
  const [sort, setSort] = useState('name');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  useEffect(() => {
    ownerApi.subscribers().then((data) => setRows(data.subscribers || [])).catch((reason) => setError(reason.message));
  }, []);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const filtered = rows.filter((row) => {
      const blob = `${row.business_name || ''} ${row.email || ''} ${row.tenant_id || ''}`.toLowerCase();
      return !needle || blob.includes(needle);
    });
    filtered.sort((left, right) => {
      const a = sort === 'tenant' ? left.tenant_id : (left.business_name || left.email || '');
      const b = sort === 'tenant' ? right.tenant_id : (right.business_name || right.email || '');
      return String(a).localeCompare(String(b));
    });
    return filtered;
  }, [rows, query, sort]);

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

  /** @param {any} row */
  const archive = async (row) => {
    const label = row.business_name || row.tenant_id;
    if (!window.confirm(`Hide ${label}? This blocks the owner account. It does not delete data.`)) return;
    const owner = (row.users || []).find((/** @type {any} */ user) => user.role === 'owner') || row.users?.[0];
    if (!owner?.id) {
      setError('No user id to update.');
      return;
    }
    await ownerApi.updateUser(owner.id, { status: 'blocked' });
    setNotice(`${label} is blocked.`);
    const data = await ownerApi.subscribers();
    setRows(data.subscribers || []);
  };

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-2xl font-semibold">Tenants</h2>
          <p className="mt-1 text-sm text-slate-400">Search, sort, and export. Hiding a tenant asks for confirmation and does not delete it.</p>
        </div>
        <button type="button" onClick={exportCsv} className="rounded-lg border border-slate-600 px-3 py-2 text-sm">Export CSV</button>
      </header>
      {error && <p className="rounded-lg bg-red-950 p-3 text-sm text-red-200">{error}</p>}
      {notice && <p className="rounded-lg bg-teal-950 p-3 text-sm text-teal-100">{notice}</p>}
      <div className="flex gap-2">
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search" className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm" />
        <select value={sort} onChange={(event) => setSort(event.target.value)} className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm">
          <option value="name">Name</option>
          <option value="tenant">Tenant id</option>
        </select>
      </div>
      {visible.length === 0 ? <p className="text-sm text-slate-400">No tenants match.</p> : null}
      <ul className="space-y-2">
        {visible.map((row) => (
          <li key={row.tenant_id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-800 p-4 text-sm">
            <div>
              <p className="font-medium">{row.business_name || row.email || row.tenant_id}</p>
              <p className="text-slate-400">{row.tenant_id} · {row.membership || 'none'} · {row.messages_remaining ?? 0} messages left</p>
            </div>
            <button type="button" className="text-amber-200" onClick={() => void archive(row)}>Hide</button>
          </li>
        ))}
      </ul>
    </div>
  );
}
