import { useEffect, useState } from 'react';
import { ownerApi } from './ownerApi';

export default function OwnerActivationBanner() {
  const [report, setReport] = useState(/** @type {any} */ (null));
  const [error, setError] = useState('');

  useEffect(() => {
    let live = true;
    ownerApi
      .activationReadiness()
      .then((data) => live && setReport(data.readiness || data))
      .catch((reason) => live && setError(reason instanceof Error ? reason.message : String(reason)));
    return () => {
      live = false;
    };
  }, []);

  if (error) {
    return (
      <p role="alert" className="rounded-lg bg-amber-950 p-3 text-sm text-amber-100">
        Activation report unavailable: {error}
      </p>
    );
  }
  if (!report) return null;
  const blockers = report.blockers || report.catalog_unconfigured || [];
  const failedImports = Object.entries(report.imports || {})
    .filter(([, ok]) => !ok)
    .map(([name]) => name);
  const missingTables = Object.entries(report.durable_tables?.tables || {})
    .filter(([, ok]) => !ok)
    .map(([name]) => name);
  return (
    <section className="rounded-xl border border-amber-900 bg-amber-950/40 p-4 text-sm text-amber-100">
      <p className="font-semibold">Activation stays off</p>
      <p className="mt-1 text-amber-200/90">
        ready_to_enable={String(Boolean(report.ready_to_enable))} · flags never flipped by this page.
        Store {report.store || '—'} · alembic {report.alembic?.ok ? 'ok' : 'check'}.
        {report.outbox
          ? ` Outbox accepted ${report.outbox.accepted || 0} · pending settlement ${report.outbox.pending_settlement || 0}.`
          : ''}
      </p>
      <p className="mt-1 text-amber-200/80">
        Conversion {report.conversion?.blocked ? 'blocked' : 'open'} ({report.conversion?.reason || '—'}).
        Catalog published={String(Boolean(report.catalog?.published))} · checkout_ready=
        {String(Boolean(report.catalog?.checkout_ready))}.
      </p>
      {report.durable_tables ? (
        <p className="mt-1 text-amber-200/80">
          Durable tables ready={String(Boolean(report.durable_tables.ready))}
          {missingTables.length ? ` · missing ${missingTables.join(', ')}` : ''}.
        </p>
      ) : null}
      {report.verification ? (
        <p className="mt-1 text-amber-200/80">
          Eval suite complete={String(Boolean(report.verification.eval_suite_complete))} · live channel
          proof={String(Boolean(report.verification.live_channel_proof))} · Voyage/pgvector=
          {String(Boolean(report.verification.live_voyage_pgvector))}.
        </p>
      ) : null}
      {failedImports.length ? (
        <p className="mt-1 text-amber-200/80">Failed imports: {failedImports.join(', ')}</p>
      ) : null}
      {blockers.length ? (
        <p className="mt-2 text-amber-200/80">Blockers: {blockers.join(', ')}</p>
      ) : null}
    </section>
  );
}
