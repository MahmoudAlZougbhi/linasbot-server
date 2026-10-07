import { useEffect, useState } from 'react';
import { ownerApi } from './ownerApi';
import { readinessLabel } from './ownerLabels';

export default function OwnerActivationBanner() {
  const [report, setReport] = useState(/** @type {any} */ (null));
  const [open, setOpen] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let live = true;
    ownerApi.activationReadiness()
      .then((data) => live && setReport(data.readiness || data))
      .catch((reason) => live && setError(reason instanceof Error ? reason.message : String(reason)));
    return () => { live = false; };
  }, []);

  if (error) {
    return <p role="alert" className="rounded-lg bg-amber-950 p-3 text-sm text-amber-100">Activation status unavailable.</p>;
  }
  if (!report) return null;
  const ready = Boolean(report.ready_to_enable);
  const blockers = (report.blockers || []).map((/** @type {string} */ key) => readinessLabel(key));
  return (
    <section className={`rounded-xl border p-4 text-sm ${ready ? 'border-teal-900 bg-teal-950/30' : 'border-amber-900 bg-amber-950/40'}`}>
      <button type="button" className="flex w-full items-center justify-between text-left" onClick={() => setOpen((value) => !value)}>
        <span className="font-semibold">{ready ? 'Activation is on' : 'Activation is off'}</span>
        <span className="text-xs opacity-70">{open ? 'Hide' : 'Details'}</span>
      </button>
      <p className="mt-1 opacity-80">
        {ready ? 'Production cutover checks passed.' : `${blockers.length} checks still need attention.`}
      </p>
      {open && blockers.length ? (
        <ul className="mt-3 list-disc space-y-1 pl-5">
          {blockers.map((/** @type {string} */ item) => <li key={item}>{item}</li>)}
        </ul>
      ) : null}
    </section>
  );
}
