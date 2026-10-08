// @ts-nocheck
import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';

/** @param {{ title: string, subtitle?: string, actions?: import('react').ReactNode }} props */
export default function PageHeader({ title, subtitle, actions }) {
  const [host, setHost] = useState(/** @type {HTMLElement | null} */ (null));
  useEffect(() => {
    setHost(document.getElementById('owner-page-header'));
  }, []);
  const body = (
    <div className="flex min-w-0 flex-1 flex-wrap items-center justify-between gap-3">
      <div className="min-w-0">
        <h1 className="truncate text-2xl font-semibold leading-8 text-slate-900">{title}</h1>
        {subtitle ? <p className="truncate text-sm text-slate-600" title={subtitle}>{subtitle}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
  if (!host) return <div className="mb-4">{body}</div>;
  return createPortal(body, host);
}
