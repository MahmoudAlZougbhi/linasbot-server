import { useEffect, useId, useRef, useState } from 'react';
import { PUBLIC_SITE } from '../../constants/publicSite';

/**
 * Enterprise / custom plan request — name, email, phone, company → mailto submit.
 * @param {{ open: boolean, onClose: () => void }} props
 */
export default function PricingEnterpriseModal({ open, onClose }) {
  const titleId = useId();
  const firstRef = useRef(/** @type {HTMLInputElement | null} */ (null));
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [company, setCompany] = useState('');
  const [sent, setSent] = useState(false);

  useEffect(() => {
    if (!open) return undefined;
    setSent(false);
    const t = window.setTimeout(() => firstRef.current?.focus(), 30);
    const onKey = (/** @type {KeyboardEvent} */ e) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => {
      window.clearTimeout(t);
      document.removeEventListener('keydown', onKey);
    };
  }, [open, onClose]);

  if (!open) return null;

  /** @param {import('react').FormEvent<HTMLFormElement>} e */
  const onSubmit = (e) => {
    e.preventDefault();
    const subject = encodeURIComponent('Linas AI — Enterprise / custom plan request');
    const body = encodeURIComponent(
      [`Name: ${name.trim()}`, `Email: ${email.trim()}`, `Phone: ${phone.trim()}`, `Company: ${company.trim()}`].join(
        '\n',
      ),
    );
    window.location.href = `mailto:${PUBLIC_SITE.contactEmail}?subject=${subject}&body=${body}`;
    setSent(true);
  };

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center p-4" role="presentation">
      <button type="button" className="absolute inset-0 bg-[#171A19]/55" aria-label="Close dialog" onClick={onClose} />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="relative z-[1] w-full max-w-md rounded-[1.35rem] bg-white p-6 shadow-[0_24px_60px_rgba(23,26,25,0.22)]"
      >
        <h3 id={titleId} className="text-xl font-semibold tracking-tight text-[#171A19]">
          Request a custom plan
        </h3>
        <p className="mt-1.5 text-sm text-[#6B746F]">
          Tell us about your business. We will follow up at {PUBLIC_SITE.contactEmail}.
        </p>

        {sent ? (
          <p className="mt-6 text-sm text-[#06715F]" role="status">
            Your email app should open with the request. If it does not, email us directly.
          </p>
        ) : (
          <form className="mt-5 space-y-3" onSubmit={onSubmit}>
            <label className="block text-sm font-medium text-[#3A4240]">
              Full name
              <input
                ref={firstRef}
                required
                value={name}
                onChange={(ev) => setName(ev.target.value)}
                className="mt-1 w-full rounded-xl border border-[#E4E8E6] px-3 py-2.5 text-[#171A19] outline-none focus:border-[#06715F] focus:ring-2 focus:ring-[#06715F]/20"
                autoComplete="name"
              />
            </label>
            <label className="block text-sm font-medium text-[#3A4240]">
              Email
              <input
                required
                type="email"
                value={email}
                onChange={(ev) => setEmail(ev.target.value)}
                className="mt-1 w-full rounded-xl border border-[#E4E8E6] px-3 py-2.5 text-[#171A19] outline-none focus:border-[#06715F] focus:ring-2 focus:ring-[#06715F]/20"
                autoComplete="email"
              />
            </label>
            <label className="block text-sm font-medium text-[#3A4240]">
              Phone
              <input
                required
                type="tel"
                value={phone}
                onChange={(ev) => setPhone(ev.target.value)}
                className="mt-1 w-full rounded-xl border border-[#E4E8E6] px-3 py-2.5 text-[#171A19] outline-none focus:border-[#06715F] focus:ring-2 focus:ring-[#06715F]/20"
                autoComplete="tel"
              />
            </label>
            <label className="block text-sm font-medium text-[#3A4240]">
              Company name
              <input
                required
                value={company}
                onChange={(ev) => setCompany(ev.target.value)}
                className="mt-1 w-full rounded-xl border border-[#E4E8E6] px-3 py-2.5 text-[#171A19] outline-none focus:border-[#06715F] focus:ring-2 focus:ring-[#06715F]/20"
                autoComplete="organization"
              />
            </label>
            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={onClose}
                className="rounded-full px-4 py-2 text-sm font-semibold text-[#5C6663] hover:bg-[#F3F5F2]"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="rounded-full bg-[#06715F] px-5 py-2.5 text-sm font-semibold text-white hover:bg-[#055a4c]"
              >
                Submit
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
