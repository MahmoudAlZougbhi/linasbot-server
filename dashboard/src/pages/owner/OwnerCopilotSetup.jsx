export default function OwnerCopilotSetup() {
  return (
    <div className="max-w-3xl space-y-6">
      <header>
        <h2 className="text-2xl font-semibold">Owner Copilot Setup</h2>
        <p className="mt-1 text-sm text-slate-400">Knowledge, behavior, files, and prompt governance for the AI that talks to business owners.</p>
      </header>
      <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
        <h3 className="font-semibold">Current runtime source</h3>
        <p className="mt-2 text-sm text-slate-300">
          Owner Copilot currently reads its base behavior from <code>services/owner_ai_context.py</code> and product
          knowledge from the system capability registry. This page does not pretend that a draft is live.
        </p>
      </section>
      <section className="rounded-xl border border-amber-800 bg-amber-950/40 p-5">
        <p className="text-xs font-semibold uppercase tracking-wide text-amber-400">Blocked safely</p>
        <h3 className="mt-2 font-semibold">Publishing is disabled in this MVP</h3>
        <p className="mt-2 text-sm text-amber-100">
          A durable HA-safe configuration source is missing. Adding portal-managed prompt/files requires a reviewed
          database schema and production migration; using local node files would break two-node consistency. No hidden
          fallback or dual prompt source was added.
        </p>
      </section>
      <section className="grid gap-3 sm:grid-cols-2">
        {[
          ['Files / knowledge', 'Requires versioned durable storage and retrieval indexing.'],
          ['How it talks', 'Requires published prompt version with audit history.'],
          ['How it acts', 'Requires validated tool-policy configuration.'],
          ['Publish workflow', 'Requires draft → validate → publish → rollback semantics.'],
        ].map(([title, description]) => (
          <article key={title} className="rounded-xl border border-slate-800 bg-slate-900 p-4">
            <h3 className="font-medium">{title}</h3>
            <p className="mt-2 text-sm text-slate-400">{description}</p>
          </article>
        ))}
      </section>
    </div>
  );
}
