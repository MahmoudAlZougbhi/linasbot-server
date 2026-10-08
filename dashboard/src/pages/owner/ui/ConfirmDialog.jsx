// @ts-nocheck
import { useEffect, useRef, useState } from 'react';
import Button from './Button';

/** @param {{ title: string, body: string, confirmLabel: string, onConfirm: () => void | Promise<void>, onClose: () => void, busy?: boolean, loadingLabel?: string }} props */
export default function ConfirmDialog({ title, body, confirmLabel, onConfirm, onClose, busy = false, loadingLabel = 'Saving…' }) {
  const cancelRef = useRef(/** @type {HTMLButtonElement | null} */ (null));
  const [pending, setPending] = useState(false);
  useEffect(() => {
    cancelRef.current?.focus();
    const onKey = (/** @type {KeyboardEvent} */ event) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-slate-900/40 p-4" role="presentation">
      <div role="alertdialog" aria-modal="true" aria-labelledby="confirm-title" className="w-full max-w-md rounded-xl bg-white p-5 shadow-sm">
        <h2 id="confirm-title" className="text-base font-semibold text-slate-900">{title}</h2>
        <p className="mt-2 text-sm leading-[22px] text-slate-700">{body}</p>
        <div className="mt-5 flex justify-end gap-3">
          <button ref={cancelRef} type="button" onClick={onClose} className="h-9 rounded-lg border border-[#CBD5E1] bg-white px-3.5 text-sm font-medium">Cancel</button>
          <Button
            variant="danger"
            loading={busy || pending}
            loadingLabel={loadingLabel}
            onClick={() => {
              setPending(true);
              Promise.resolve(onConfirm()).finally(() => setPending(false));
            }}
          >
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
