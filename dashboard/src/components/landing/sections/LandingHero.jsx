import { useEffect, useState } from 'react';
import { PUBLIC_SITE } from '../../../constants/publicSite';
import { CHANNELS } from '../ChannelIcons';
import LinasStar from '../LinasStar';
import StoreBadges from '../StoreBadges';
import { usePrefersReducedMotion } from '../../../hooks/usePrefersReducedMotion';

const LINES = [
  { role: 'linas', text: 'What would you like to teach me about your business?' },
  { role: 'you', text: "We're closed tomorrow." },
  { role: 'linas', text: 'Done — I added tomorrow as an off day.' },
  { role: 'you', text: 'If someone asks how long we’ve been in business, tell them the company was founded in 1977.' },
  { role: 'linas', text: 'Got it — I saved this in your Business Knowledge.' },
];

export default function LandingHero() {
  const reduced = usePrefersReducedMotion();
  const [visible, setVisible] = useState(reduced ? LINES.length : 0);

  useEffect(() => {
    if (reduced) {
      setVisible(LINES.length);
      return undefined;
    }
    setVisible(0);
    const timers = LINES.map((_, i) => setTimeout(() => setVisible(i + 1), 450 + i * 700));
    return () => timers.forEach(clearTimeout);
  }, [reduced]);

  return (
    <section className="relative overflow-hidden bg-[#F7F8F5]">
      <div className="pointer-events-none absolute inset-0" aria-hidden="true">
        <div className="absolute -right-24 top-10 h-[28rem] w-[28rem] rounded-full bg-[#D7EFE8]/70 blur-3xl" />
        <div className="absolute right-[12%] top-24 h-[36rem] w-[36rem] rounded-full border border-[#06715F]/10" />
        <LinasStar className="absolute right-[18%] top-16 h-6 w-6 opacity-70" />
        <LinasStar className="absolute bottom-24 left-[42%] h-4 w-4 opacity-40" />
      </div>

      <div className="relative mx-auto grid max-w-6xl items-center gap-12 px-4 pb-16 pt-10 sm:px-6 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)] lg:pb-24 lg:pt-14">
        <div>
          <p className="text-sm font-semibold text-[#06715F]">{PUBLIC_SITE.heroKicker}</p>
          <h1 className="mt-4 max-w-xl text-4xl font-semibold tracking-tight text-[#171A19] sm:text-5xl lg:text-[3.35rem] lg:leading-[1.08]">
            Talk to Linas. Linas talks to <span className="text-[#06715F]">your customers.</span>
          </h1>
          <p className="mt-5 max-w-lg text-base leading-relaxed text-[#5C6663] sm:text-lg">{PUBLIC_SITE.heroSupport}</p>
          <div className="mt-8">
            <StoreBadges variant="hero" />
          </div>
          <div className="mt-8 max-w-lg rounded-2xl border border-[#E4E8E6] bg-white p-4 shadow-sm">
            <p className="text-sm text-[#5C6663]">Connect the AI you train in Linas to reply on:</p>
            <div className="mt-3 flex flex-wrap gap-4">
              {CHANNELS.map((ch) => (
                <div key={ch.id} className="flex flex-col items-center gap-1">
                  <ch.Icon className="h-8 w-8" />
                  <span className="text-[0.65rem] font-medium text-[#5C6663]">{ch.label}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="mx-auto w-full max-w-[22rem]">
          <div className="rounded-[1.8rem] border border-black/10 bg-white p-4 shadow-2xl shadow-[#06715F]/10">
            <div className="mb-3 flex items-center gap-2 text-[#171A19]">
              <span className="text-lg">☰</span>
            </div>
            <div className="min-h-[22rem] space-y-3">
              {LINES.slice(0, visible).map((line) =>
                line.role === 'you' ? (
                  <div key={line.text} className="lp-fade-up flex justify-end">
                    <div>
                      <p className="mb-1 text-right text-[0.65rem] text-[#8A938F]">You</p>
                      <p className="max-w-[16rem] rounded-2xl bg-[#D7EFE8] px-3 py-2 text-sm text-[#171A19]">{line.text}</p>
                    </div>
                  </div>
                ) : (
                  <div key={line.text} className="lp-fade-up">
                    <p className="mb-1 flex items-center gap-1 text-[0.65rem] text-[#06715F]">
                      <LinasStar className="h-3.5 w-3.5" /> Linas
                    </p>
                    <p className="text-sm leading-relaxed text-[#171A19]">{line.text}</p>
                  </div>
                ),
              )}
            </div>
            <div className="mt-3 flex items-center gap-2 rounded-full border border-[#E4E8E6] px-3 py-2">
              <span className="text-[#8A938F]">+</span>
              <span className="flex-1 text-sm text-[#8A938F]">Work with Linas</span>
              <span className="text-[#8A938F]">🎤</span>
              <span className="flex h-8 w-8 items-center justify-center rounded-full bg-[#06715F] text-white">↑</span>
            </div>
            <p className="mt-2 text-center text-[0.65rem] text-[#8A938F]">Linas can make mistakes. Check important info.</p>
          </div>
        </div>
      </div>
    </section>
  );
}
