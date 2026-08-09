import { useState } from 'react';
import { PUBLIC_SITE } from '../../../constants/publicSite';

const FAQS = [
  {
    q: 'What exactly does Linas AI do?',
    a: 'Linas AI answers customer DMs and comments on Facebook and Instagram using business facts your team approves. Setup and control stay in one chat-first Owner Copilot in the mobile app.',
  },
  {
    q: 'Does it create posts, Stories, Reels, or videos?',
    a: 'No. Linas AI is built for messaging conversations only — Messenger DMs, Instagram DMs, and comments. It does not publish posts, Stories, Reels, or videos.',
  },
  {
    q: 'Can I try it before creating an account?',
    a: 'Yes. Use Guest AI on this site for a limited product conversation (10 prompts). Day-to-day work and subscriptions live in the Linas AI app — this website has no signup.',
  },
  {
    q: 'Can team members manually reply from Live Chat?',
    a: 'Live Chat is a read-only audit surface for inspecting what customers asked and what Linas answered. It is not a manual reply inbox.',
  },
  {
    q: 'How are prices and limits shown?',
    a: 'Live amounts, currencies, limits, and purchase routes come from the billing catalog at checkout in the app. This marketing page does not invent prices.',
  },
];

/** FAQ + contact — matches linas-landing-08-contact.jpg */
export default function LandingFaqContact() {
  const [open, setOpen] = useState(/** @type {string | null} */ (FAQS[0].q));
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [message, setMessage] = useState('');

  /** @param {import('react').FormEvent<HTMLFormElement>} event */
  const onSubmit = (event) => {
    event.preventDefault();
    const subject = encodeURIComponent(`Linas AI inquiry from ${name || 'website'}`);
    const body = encodeURIComponent(`Name: ${name}\nEmail: ${email}\n\n${message}`);
    window.location.href = `mailto:${PUBLIC_SITE.contactEmail}?subject=${subject}&body=${body}`;
  };

  return (
    <section id="contact" className="scroll-mt-24 bg-white py-20 sm:py-24">
      <div className="mx-auto grid max-w-6xl gap-12 px-4 sm:px-6 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)]">
        <div>
          <h2 className="text-3xl font-semibold tracking-tight text-[#171A19] sm:text-4xl">
            Get answers before you begin.
          </h2>
          <div className="mt-8 divide-y divide-[#E4E8E6] border-y border-[#E4E8E6]">
            {FAQS.map((item) => {
              const isOpen = open === item.q;
              return (
                <div key={item.q}>
                  <button
                    type="button"
                    className="flex w-full items-center justify-between gap-4 py-4 text-left text-base font-semibold text-[#171A19] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#06715F]"
                    aria-expanded={isOpen}
                    onClick={() => setOpen(isOpen ? null : item.q)}
                  >
                    {item.q}
                    <span className="text-xl font-normal text-[#8A938F]" aria-hidden="true">
                      {isOpen ? '−' : '+'}
                    </span>
                  </button>
                  {isOpen && <p className="pb-4 text-sm leading-relaxed text-[#5C6663]">{item.a}</p>}
                </div>
              );
            })}
          </div>
        </div>

        <div className="rounded-[1.75rem] bg-[#171A19] p-6 text-white sm:p-8">
          <p className="text-[0.7rem] font-semibold uppercase tracking-[0.16em] text-[#54C7AC]">Contact us</p>
          <h3 className="mt-2 text-2xl font-semibold tracking-tight">Tell us what your team needs.</h3>
          <p className="mt-3 text-sm leading-relaxed text-white/65">
            Share your channels, expected conversation volume, and setup questions. A verified Linas AI contact route will
            receive the request in production.
          </p>
          <form className="mt-6 space-y-3" onSubmit={onSubmit}>
            <label className="block">
              <span className="sr-only">Name</span>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Your name"
                className="w-full rounded-xl border border-white/15 bg-white/5 px-4 py-3 text-sm text-white placeholder:text-white/40 focus:border-[#54C7AC] focus:outline-none"
                required
              />
            </label>
            <label className="block">
              <span className="sr-only">Work email</span>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@company.com"
                className="w-full rounded-xl border border-white/15 bg-white/5 px-4 py-3 text-sm text-white placeholder:text-white/40 focus:border-[#54C7AC] focus:outline-none"
                required
              />
            </label>
            <label className="block">
              <span className="sr-only">How can we help?</span>
              <textarea
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder="Tell us about your business and channels"
                rows={4}
                className="w-full resize-y rounded-xl border border-white/15 bg-white/5 px-4 py-3 text-sm text-white placeholder:text-white/40 focus:border-[#54C7AC] focus:outline-none"
                required
              />
            </label>
            <button
              type="submit"
              className="w-full rounded-full bg-[#06715F] px-5 py-3 text-sm font-semibold text-white hover:bg-[#0B3D34] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#54C7AC]"
            >
              Send message →
            </button>
          </form>
        </div>
      </div>
    </section>
  );
}
