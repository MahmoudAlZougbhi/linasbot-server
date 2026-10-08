// @ts-nocheck
import { useMemo, useState } from 'react';
import { MagnifyingGlassIcon } from '@heroicons/react/24/outline';
import Button from './Button';
import { SkeletonRows } from './Skeleton';

/**
 * @param {{
 *  columns: { key: string, label: string, render?: (row: any) => import('react').ReactNode, align?: string }[],
 *  rows: any[],
 *  getRowId: (row: any) => string,
 *  loading?: boolean,
 *  error?: import('react').ReactNode,
 *  empty?: import('react').ReactNode,
 *  searchPlaceholder?: string,
 *  searchText?: (row: any) => string,
 *  toolbar?: import('react').ReactNode,
 *  onRowClick?: (row: any) => void,
 *  pageSize?: number,
 * }} props
 */
export default function DataTable({
  columns,
  rows,
  getRowId,
  loading = false,
  error = null,
  empty = null,
  searchPlaceholder = 'Search',
  searchText = (row) => JSON.stringify(row),
  toolbar = null,
  onRowClick,
  pageSize = 25,
  countNoun = 'rows',
}) {
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(0);
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return rows;
    return rows.filter((row) => searchText(row).toLowerCase().includes(needle));
  }, [rows, query, searchText]);
  const start = page * pageSize;
  const visible = filtered.slice(start, start + pageSize);
  const countLabel = loading ? 'Loading…' : `${filtered.length} ${countNoun}`;
  return (
    <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="flex flex-wrap items-center gap-3 border-b border-slate-200 p-4">
        <label className="relative min-w-[220px] flex-1">
          <span className="sr-only">{searchPlaceholder}</span>
          <MagnifyingGlassIcon className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-500" />
          <input
            value={query}
            onChange={(event) => { setQuery(event.target.value); setPage(0); }}
            placeholder={searchPlaceholder}
            className="h-9 w-full rounded-lg border border-[#7C8798] pl-9 pr-3 text-sm"
          />
        </label>
        {toolbar}
        <p className="ml-auto text-sm text-slate-600">{countLabel}</p>
      </div>
      {loading ? <div className="p-4"><SkeletonRows /></div> : null}
      {!loading && error}
      {!loading && !error && filtered.length === 0 ? empty : null}
      {!loading && !error && filtered.length > 0 ? (
        <>
          <div className="hidden md:block">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-100 text-[13px] font-semibold text-slate-600">
                <tr>{columns.map((column) => <th key={column.key} className={`px-4 py-3 ${column.align === 'right' ? 'text-right' : ''}`}>{column.label}</th>)}</tr>
              </thead>
              <tbody>
                {visible.map((row) => (
                  <tr
                    key={getRowId(row)}
                    tabIndex={onRowClick ? 0 : undefined}
                    onClick={() => onRowClick?.(row)}
                    onKeyDown={(event) => {
                      if (onRowClick && (event.key === 'Enter' || event.key === ' ')) {
                        event.preventDefault();
                        onRowClick(row);
                      }
                    }}
                    className="border-t border-slate-100 hover:bg-slate-50"
                  >
                    {columns.map((column) => (
                      <td key={column.key} className={`px-4 py-3 text-slate-700 ${column.align === 'right' ? 'text-right tabular-nums' : ''}`}>
                        {column.render ? column.render(row) : row[column.key]}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="space-y-3 p-4 md:hidden">
            {visible.map((row) => (
              <button key={getRowId(row)} type="button" onClick={() => onRowClick?.(row)} className="w-full rounded-lg bg-slate-50 p-3 text-left">
                {columns.map((column) => (
                  <p key={column.key} className="text-sm text-slate-700"><span className="text-slate-600">{column.label}: </span>{column.render ? column.render(row) : row[column.key]}</p>
                ))}
              </button>
            ))}
          </div>
          <div className="flex items-center justify-between border-t border-slate-100 px-4 py-3 text-sm text-slate-600">
            <span>Showing {filtered.length ? start + 1 : 0}–{Math.min(start + pageSize, filtered.length)} of {filtered.length}</span>
            <div className="flex gap-2">
              <Button variant="secondary" disabled={page === 0} onClick={() => setPage((current) => current - 1)}>Previous</Button>
              <Button variant="secondary" disabled={start + pageSize >= filtered.length} onClick={() => setPage((current) => current + 1)}>Next</Button>
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}
