import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  BuildingOffice2Icon,
  ChatBubbleLeftRightIcon,
  CheckBadgeIcon,
  DevicePhoneMobileIcon,
  LinkIcon,
  ShieldCheckIcon,
} from '@heroicons/react/24/outline';
import PublicSiteHeader from '../../components/landing/PublicSiteHeader';
import PublicSiteFooter from '../../components/landing/PublicSiteFooter';
import GuestChatPanel from '../../components/landing/GuestChatPanel';
import StoreBadges from '../../components/landing/StoreBadges';
import { LINAS_BRAND_ASSETS } from '../../constants/linasBrand';
import { PUBLIC_PATHS, PUBLIC_SITE, STORE_LINKS } from '../../constants/publicSite';

const steps = [
  {
    title: 'Download the Linas AI app',
    body: 'Get Linas on iOS or Android — the full product lives in the mobile app, not on this website.',
  },
  {
    title: 'Subscribe in the app',
    body: 'Choose a plan and unlock owner chat, Content Management, messaging, and creative tools.',
  },
  {
    title: 'Connect Facebook & Instagram',
    body: 'Connect a Facebook Page and Instagram Professional Account you own or are authorized to manage.',
  },
  {
    title: 'Teach Linas your business',
    body: 'Publish services, prices, branches, hours, and FAQs. Linas replies to private DMs from that approved content.',
  },
];

const features = [
  {
    icon: ChatBubbleLeftRightIcon,
    title: 'Private-message AI replies',
    body: 'Respond to customer-initiated Messenger and Instagram DMs. Comment replies stay gated until Meta review.',
  },
  {
    icon: BuildingOffice2Icon,
    title: 'Business-controlled content',
    body: 'Each company trains replies from its own approved services, prices, branches, hours, and FAQs.',
  },
  {
    icon: DevicePhoneMobileIcon,
    title: 'App-first workspace',
    body: 'Operate Linas from your phone — setup, billing, and daily control happen in the mobile app.',
  },
  {
    icon: LinkIcon,
    title: 'Human and booking handoff',
    body: 'When booking or human help is needed, customers are directed to the contact channel your company chooses.',
  },
  {
    icon: ShieldCheckIcon,
    title: 'Disconnect and delete on request',
    body: 'Disconnect Meta accounts from the product and follow published data-deletion instructions anytime.',
  },
];

const faqs = [
  {
    q: 'Can I create an account on this website?',
    a: 'No. The public website is marketing and a limited guest chat. Download the Linas AI app to subscribe and run your business workspace.',
  },
  {
    q: 'Does Linas AI reply to comments?',
    a: 'Private Messenger and Instagram DMs are in scope. Comment automation stays gated until Meta App Review and live verification.',
  },
  {
    q: 'Who controls what the AI says?',
    a: 'Each business controls its approved company information. Replies use that published content for that business only.',
  },
  {
    q: 'What is the guest chat for?',
    a: 'Try a short product conversation with Linas (10 questions, 50 words each). It explains Linas AI — it does not change any business workspace.',
  },
  {
    q: 'How do I request data deletion?',
    a: 'Use the Data Deletion instructions page, remove the app through Meta settings, or email the contact address published on that page.',
  },
];

const Landing = () => {
  return (
    <div className="min-h-screen bg-[#F7F4FC] text-[#2A1B4A]">
      <div className="pointer-events-none fixed inset-0 overflow-hidden" aria-hidden="true">
        <div className="absolute -right-32 -top-24 h-[28rem] w-[28rem] rounded-full bg-[#C4B0FF]/35 blur-3xl" />
        <div className="absolute -bottom-40 -left-20 h-[24rem] w-[24rem] rounded-full bg-[#7EC8E8]/25 blur-3xl" />
        <div className="absolute left-1/3 top-1/3 h-64 w-64 rounded-full bg-[#6D4AFF]/10 blur-3xl" />
      </div>

      <PublicSiteHeader />

      <main>
        {/* Full-bleed brand-first hero */}
        <section className="relative min-h-[min(92vh,56rem)] overflow-hidden border-b border-[#E4DCF2]">
          <div
            className="absolute inset-0 bg-cover bg-center bg-no-repeat"
            style={{
              backgroundImage: `linear-gradient(105deg, rgba(247,244,252,0.92) 0%, rgba(247,244,252,0.78) 38%, rgba(109,74,255,0.18) 100%), url(${LINAS_BRAND_ASSETS.hero})`,
            }}
            aria-hidden="true"
          />
          <div className="absolute inset-0 bg-gradient-to-t from-[#F7F4FC] via-transparent to-[#F7F4FC]/40" aria-hidden="true" />

          <div className="relative mx-auto flex min-h-[min(92vh,56rem)] max-w-6xl flex-col justify-end px-4 pb-16 pt-24 sm:px-6 lg:justify-center lg:pb-24 lg:pt-20">
            <motion.div
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5 }}
              className="max-w-xl"
            >
              <p className="font-display text-5xl font-bold tracking-tight text-[#2A1B4A] sm:text-6xl lg:text-7xl">
                {PUBLIC_SITE.heroTitle}
              </p>
              <h1 className="mt-4 max-w-lg font-display text-2xl font-semibold leading-snug text-[#3D2A6D] sm:text-3xl">
                {PUBLIC_SITE.heroHeadline}
              </h1>
              <p className="mt-4 max-w-lg text-base leading-relaxed text-[#6B5B85] sm:text-lg">
                {PUBLIC_SITE.heroSupport}
              </p>
              <div className="mt-8 flex flex-wrap items-center gap-3">
                <a
                  href="#talk-to-linas"
                  className="rounded-xl bg-[#6D4AFF] px-5 py-3 text-base font-semibold text-white shadow-lg shadow-[#6D4AFF]/30 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#6D4AFF] focus-visible:ring-offset-2"
                >
                  Talk to Linas
                </a>
                <a
                  href="#get-app"
                  className="rounded-xl border border-[#E4DCF2] bg-white/90 px-5 py-3 text-base font-semibold text-[#2A1B4A] backdrop-blur hover:bg-white focus:outline-none focus-visible:ring-2 focus-visible:ring-[#6D4AFF]"
                >
                  Get the app
                </a>
              </div>
              <div className="mt-6">
                <StoreBadges />
              </div>
              {(STORE_LINKS.appStore.status !== 'live' || STORE_LINKS.playStore.status !== 'live') && (
                <p className="mt-3 max-w-md text-xs text-[#9B8BB5]">
                  Store badges show Coming soon until App Store / Play listings are public. Bundle/package:{' '}
                  <span className="font-mono">com.linasai.app</span>
                </p>
              )}
            </motion.div>

            <motion.img
              initial={{ opacity: 0, y: 24 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.55, delay: 0.12 }}
              src={LINAS_BRAND_ASSETS.welcome}
              alt="Linas AI character"
              className="pointer-events-none absolute bottom-0 right-[-4%] hidden w-[min(42%,28rem)] drop-shadow-2xl lg:block"
              width={448}
              height={448}
            />
          </div>
        </section>

        <section className="relative py-16 sm:py-20">
          <div className="mx-auto max-w-6xl px-4 sm:px-6">
            <GuestChatPanel />
          </div>
        </section>

        <section id="how-it-works" className="border-y border-[#E4DCF2] bg-white/70 py-16">
          <div className="mx-auto max-w-6xl px-4 sm:px-6">
            <h2 className="font-display text-3xl font-bold text-[#2A1B4A]">How it works</h2>
            <p className="mt-3 max-w-2xl text-[#6B5B85]">
              Download the app, subscribe, connect Meta, and publish the business knowledge Linas uses for private replies.
            </p>
            <ol className="mt-10 grid gap-6 md:grid-cols-2">
              {steps.map((step, index) => (
                <li key={step.title} className="rounded-2xl border border-[#E4DCF2] bg-[#F7F4FC]/90 p-6">
                  <p className="text-sm font-semibold uppercase tracking-wide text-[#6D4AFF]">Step {index + 1}</p>
                  <h3 className="mt-2 font-display text-xl font-semibold text-[#2A1B4A]">{step.title}</h3>
                  <p className="mt-2 text-[#6B5B85]">{step.body}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section id="features" className="py-16">
          <div className="mx-auto max-w-6xl px-4 sm:px-6">
            <h2 className="font-display text-3xl font-bold text-[#2A1B4A]">Features</h2>
            <p className="mt-3 max-w-2xl text-[#6B5B85]">
              Built for private customer messaging on Facebook and Instagram — operated from the Linas AI app.
            </p>
            <div className="mt-10 grid gap-6 md:grid-cols-2">
              {features.map((feature) => {
                const Icon = feature.icon;
                return (
                  <article key={feature.title} className="rounded-2xl border border-[#E4DCF2] bg-white/80 p-6">
                    <Icon className="h-7 w-7 text-[#6D4AFF]" aria-hidden="true" />
                    <h3 className="mt-4 font-display text-xl font-semibold text-[#2A1B4A]">{feature.title}</h3>
                    <p className="mt-2 text-[#6B5B85]">{feature.body}</p>
                  </article>
                );
              })}
            </div>
          </div>
        </section>

        <section id="pricing" className="border-y border-[#E4DCF2] bg-white/70 py-16">
          <div className="mx-auto max-w-6xl px-4 sm:px-6">
            <h2 className="font-display text-3xl font-bold text-[#2A1B4A]">Pricing</h2>
            <p className="mt-3 max-w-3xl text-[#6B5B85]">
              Subscriptions and usage credits are managed in the Linas AI mobile app — not via website signup.
              See the{' '}
              <Link className="font-semibold text-[#6D4AFF] underline" to={PUBLIC_PATHS.pricing}>
                pricing page
              </Link>{' '}
              for plan overview, then subscribe in the app.
            </p>
            <div className="mt-8">
              <StoreBadges />
            </div>
          </div>
        </section>

        <section id="meta-connection" className="py-16">
          <div className="mx-auto max-w-6xl px-4 sm:px-6">
            <h2 className="font-display text-3xl font-bold text-[#2A1B4A]">Facebook & Instagram</h2>
            <p className="mt-3 max-w-3xl text-[#6B5B85]">
              In the app, connect the Facebook Page and Instagram Professional Account your business owns or is
              authorized to manage. Connection uses Meta Business Login. You can disconnect those accounts when you no
              longer want Linas AI to receive or reply to their private messages.
            </p>
          </div>
        </section>

        <section id="training" className="border-y border-[#E4DCF2] bg-white/70 py-16">
          <div className="mx-auto max-w-6xl px-4 sm:px-6">
            <h2 className="font-display text-3xl font-bold text-[#2A1B4A]">Business-controlled AI</h2>
            <p className="mt-3 max-w-3xl text-[#6B5B85]">
              Add company information, services, prices, branches, hours, and FAQs. Publish what your team approves.
              Linas uses that published information for your tenant only.
            </p>
            <ul className="mt-6 space-y-3 text-[#6B5B85]">
              {[
                'Download Linas AI and subscribe in the app',
                'Connect authorized Facebook Page and Instagram Professional accounts',
                'Add and publish approved business information',
                'Auto-reply to Instagram private messages and Facebook Messenger',
                'Route booking or human help to your chosen contact channel',
                'Disconnect Meta accounts or request data deletion',
              ].map((item) => (
                <li key={item} className="flex items-start gap-3">
                  <CheckBadgeIcon className="mt-0.5 h-5 w-5 shrink-0 text-[#0D9488]" aria-hidden="true" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section id="privacy" className="py-16">
          <div className="mx-auto max-w-6xl px-4 sm:px-6">
            <h2 className="font-display text-3xl font-bold text-[#2A1B4A]">Privacy and data use</h2>
            <p className="mt-4 max-w-4xl text-base leading-relaxed text-[#6B5B85]">
              {PUBLIC_SITE.metaPlatformDataUse}
            </p>
            <p className="mt-4 text-sm text-[#6B5B85]">
              Read the full{' '}
              <a className="font-semibold text-[#6D4AFF] underline" href={PUBLIC_PATHS.privacy}>
                Privacy Policy
              </a>
              ,{' '}
              <a className="font-semibold text-[#6D4AFF] underline" href={PUBLIC_PATHS.terms}>
                Terms of Service
              </a>
              , and{' '}
              <a className="font-semibold text-[#6D4AFF] underline" href={PUBLIC_PATHS.dataDeletion}>
                User Data Deletion Instructions
              </a>
              .
            </p>
          </div>
        </section>

        <section id="faq" className="border-y border-[#E4DCF2] bg-white/70 py-16">
          <div className="mx-auto max-w-6xl px-4 sm:px-6">
            <h2 className="font-display text-3xl font-bold text-[#2A1B4A]">FAQ</h2>
            <div className="mt-8 space-y-4">
              {faqs.map((item) => (
                <details key={item.q} className="group rounded-2xl border border-[#E4DCF2] bg-[#F7F4FC]/90 p-5">
                  <summary className="cursor-pointer list-none rounded font-semibold text-[#2A1B4A] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#6D4AFF]">
                    {item.q}
                  </summary>
                  <p className="mt-3 text-[#6B5B85]">{item.a}</p>
                </details>
              ))}
            </div>
          </div>
        </section>

        <section id="about-provider" className="py-16">
          <div className="mx-auto max-w-6xl px-4 sm:px-6">
            <h2 className="font-display text-3xl font-bold text-[#2A1B4A]">About the provider</h2>
            <p className="mt-3 max-w-3xl text-[#6B5B85]">
              {PUBLIC_SITE.productName} is the software platform behind{' '}
              <a className="font-semibold text-[#6D4AFF] underline" href={PUBLIC_SITE.publicBaseUrl}>
                {PUBLIC_SITE.publicBaseUrl.replace('https://', '')}
              </a>
              . It helps businesses answer private Facebook Messenger and Instagram customer messages using information
              each business approves and controls.
            </p>
            <p className="mt-4">
              <Link className="font-semibold text-[#6D4AFF] underline" to={PUBLIC_PATHS.about}>
                More about {PUBLIC_SITE.productName}
              </Link>
            </p>
          </div>
        </section>

        <section id="contact" className="border-t border-[#E4DCF2] bg-white/70 py-16">
          <div className="mx-auto max-w-6xl px-4 sm:px-6">
            <h2 className="font-display text-3xl font-bold text-[#2A1B4A]">Contact</h2>
            <p className="mt-3 max-w-2xl text-[#6B5B85]">
              For product, privacy, or data-deletion questions, email{' '}
              <a className="font-semibold text-[#6D4AFF] underline" href={`mailto:${PUBLIC_SITE.contactEmail}`}>
                {PUBLIC_SITE.contactEmail}
              </a>
              .
            </p>
            <p className="mt-4">
              <Link className="font-semibold text-[#6D4AFF] underline" to={PUBLIC_PATHS.contact}>
                Contact page
              </Link>
            </p>
          </div>
        </section>
      </main>

      <PublicSiteFooter />
    </div>
  );
};

export default Landing;
