import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeftIcon, ArrowPathIcon } from "@heroicons/react/24/outline";
import toast from "react-hot-toast";
import { useApi } from "../../hooks/useApi";
import { asRecord, asRecordList, statusBadgeClass } from "./cmDraftHelpers";

/**
 * Owner-visible source inventory / provenance (no JSON editor, no content bodies).
 */
const CmSourcesPage = () => {
  const { getCmSourcesInventory } = useApi();
  const [loading, setLoading] = useState(true);
  const [report, setReport] = useState(/** @type {Record<string, unknown> | null} */ (null));

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getCmSourcesInventory();
      if (!res?.success || !res.data) {
        toast.error(res?.error || "Failed to load source inventory");
        setReport(null);
        return;
      }
      setReport(asRecord(res.data));
    } finally {
      setLoading(false);
    }
  }, [getCmSourcesInventory]);

  useEffect(() => {
    void load();
  }, [load]);

  const totals = asRecord(report?.totals);
  const pointer = asRecord(report?.published_pointer);
  const articles = asRecordList(report?.article_sources);
  const staged = asRecordList(report?.staged_legacy_files);
  const scrub = asRecordList(report?.restricted_scrub_archives);
  const sections = asRecord(report?.section_counts);

  return (
    <div className="space-y-6">
      <div>
        <Link to="/content-managers" className="inline-flex items-center text-sm text-slate-500 hover:text-slate-800 mb-2">
          <ArrowLeftIcon className="w-4 h-4 mr-1" /> AI Setup
        </Link>
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-2xl font-semibold text-slate-900">Sources & Archive</h1>
            <p className="text-slate-600 mt-1 max-w-3xl">
              Where every migrated Lina’s file lives now: section, status, and checksum. Restricted files stay visible but are not used by AI.
            </p>
          </div>
          <button
            type="button"
            onClick={() => void load()}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-sm"
          >
            <ArrowPathIcon className="w-4 h-4" /> Refresh
          </button>
        </div>
      </div>

      {loading ? <p className="text-sm text-slate-500">Loading inventory…</p> : null}

      {!loading && report ? (
        <>
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {[
              ["Articles", totals.article_source_rows],
              ["Active for AI", totals.active_articles],
              ["Restricted", totals.restricted_articles],
              ["Staged legacy files", totals.staged_legacy_files],
            ].map(([label, value]) => (
              <div key={String(label)} className="rounded-2xl border border-slate-200 bg-white p-4">
                <div className="text-xs uppercase tracking-wide text-slate-500">{String(label)}</div>
                <div className="text-2xl font-semibold text-slate-900 mt-1">
                  {typeof value === "number" || typeof value === "string" ? value : 0}
                </div>
              </div>
            ))}
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-4 text-sm text-slate-700 space-y-1">
            <div>
              <span className="font-medium">Published content:</span> {String(pointer.content_version_id || "—")}
            </div>
            <div>
              <span className="font-medium">Published index:</span> {String(pointer.index_version_id || "—")}
            </div>
            <div>
              <span className="font-medium">Tenant:</span> {String(report.tenant_id || "—")}
            </div>
          </div>

          <section className="space-y-2">
            <h2 className="text-lg font-semibold text-slate-900">Section counts</h2>
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2">
              {Object.entries(sections).map(([name, raw]) => {
                const row = asRecord(raw);
                return (
                  <div key={name} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm">
                    <div className="font-medium">{name}</div>
                    <div className="text-slate-500">
                      {row.draft_present === false
                        ? "Missing draft"
                        : `items=${String(row.item_count ?? row.catalog_count ?? "—")}`}
                    </div>
                  </div>
                );
              })}
            </div>
          </section>

          <section className="space-y-2">
            <h2 className="text-lg font-semibold text-slate-900">Knowledge / Care articles</h2>
            <div className="overflow-auto rounded-2xl border border-slate-200 bg-white">
              <table className="min-w-full text-sm">
                <thead className="bg-slate-50 text-left text-slate-600">
                  <tr>
                    <th className="px-3 py-2">Title</th>
                    <th className="px-3 py-2">Status</th>
                    <th className="px-3 py-2">Source file</th>
                    <th className="px-3 py-2">Open</th>
                  </tr>
                </thead>
                <tbody>
                  {articles.map((row) => (
                    <tr key={`${row.kind}-${row.id}`} className="border-t border-slate-100">
                      <td className="px-3 py-2">{String(row.title || row.id)}</td>
                      <td className="px-3 py-2">
                        <span className={`text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full ${statusBadgeClass(String(row.status || "active"))}`}>
                          {String(row.status || "active")}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-slate-500">{String(row.source_filename || "—")}</td>
                      <td className="px-3 py-2">
                        <Link className="text-emerald-700 hover:underline" to={`/${String(row.ui_visibility || "content-managers/knowledge")}`}>
                          Open
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="space-y-2">
            <h2 className="text-lg font-semibold text-slate-900">Staged legacy files</h2>
            <ul className="space-y-2">
              {staged.map((file) => (
                <li key={`${file.relative_hint}-${file.sha256}`} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm">
                  <div className="font-medium">{String(file.filename)}</div>
                  <div className="text-slate-500">
                    → {String(file.migration_destination)} · {String(file.size_bytes)} bytes · sha256{" "}
                    {String(file.sha256 || "").slice(0, 12)}…
                  </div>
                </li>
              ))}
              {staged.length === 0 ? <li className="text-sm text-slate-500">No staged legacy copy found yet (run migration).</li> : null}
            </ul>
          </section>

          <section className="space-y-2">
            <h2 className="text-lg font-semibold text-slate-900">Restricted scrub archives</h2>
            <ul className="space-y-2">
              {scrub.map((bucket) => (
                <li key={String(bucket.bucket)} className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-900">
                  <div className="font-medium">{String(bucket.bucket)}</div>
                  <div>{asRecordList(bucket.files).length} archived file(s) — not used by AI</div>
                </li>
              ))}
              {scrub.length === 0 ? <li className="text-sm text-slate-500">No restricted scrub archive buckets.</li> : null}
            </ul>
          </section>
        </>
      ) : null}
    </div>
  );
};

export default CmSourcesPage;
