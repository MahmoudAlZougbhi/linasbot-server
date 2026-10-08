// @ts-nocheck
import { ExclamationTriangleIcon } from '@heroicons/react/24/outline';
import Button from './Button';
import TechDetails from './TechDetails';

/** @param {{ title: string, text?: string, onRetry?: () => void, detail?: string }} props */
export default function Alert({ title, text, onRetry, detail }) {
  return (
    <div role="alert" className="rounded-xl border border-red-300 bg-red-100 p-4 text-red-800">
      <div className="flex items-start gap-3">
        <ExclamationTriangleIcon className="h-5 w-5 shrink-0" />
        <div>
          <p className="text-sm font-semibold">{title}</p>
          {text ? <p className="mt-1 text-sm">{text}</p> : null}
          {onRetry ? <div className="mt-3"><Button variant="secondary" onClick={onRetry}>Try again</Button></div> : null}
          {detail ? <TechDetails text={detail} /> : null}
        </div>
      </div>
    </div>
  );
}
