import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  BuildingOffice2Icon,
  ChatBubbleLeftRightIcon,
  CheckBadgeIcon,
  LinkIcon,
  ShieldCheckIcon,
  SparklesIcon,
} from '@heroicons/react/24/outline';
import PublicSiteHeader from '../../components/landing/PublicSiteHeader';
import PublicSiteFooter from '../../components/landing/PublicSiteFooter';
import { PUBLIC_PATHS, PUBLIC_SITE } from '../../constants/publicSite';

const steps = [
  {
    title: 'Create a company account',
    body: 'Register your business and receive an isolated tenant workspace for your team.',
  },
  {
    title: 'Connect Facebook & Instagram',
    body: 'Connect a Facebook Page and Instagram Professional Account you own or are authorized to manage.',
  },
  {
    title: 'Add approved business information',
    body: 'Publish services, prices, branches, hours, FAQs, and handoff contacts your business controls.',
  },
  {
    title: 'Reply to private messages',
    body: 'Linas AI answers Instagram private messages and Facebook Messenger using only your approved content.',
  },
];

const features = [
  {
    icon: ChatBubbleLeftRightIcon,
    title: 'Private-message AI replies',
    body: 'Respond to customer-initiated Messenger and Instagram DMs. Comment replies are out of scope.',
  },
  {
    icon: BuildingOffice2Icon,
    title: 'Business-controlled content',
    body: 'Each company trains replies from its own approved services, prices, branches, hours, and FAQs.',
  },
  {
    icon: LinkIcon,
    title: 'Human and booking handoff',
    body: 'When booking or human help is needed, customers are directed to the contact channel your company chooses.',
  },
  {
    icon: ShieldCheckIcon,
    title: 'Disconnect and delete on request',
    body: 'Disconnect Meta accounts from the dashboard and follow published data-deletion instructions anytime.',
  },
];

const faqs = [
  {
    q: 'Does Linas AI reply to comments?',
    a: 'No. Linas AI processes private messages on Facebook Messenger and Instagram only. It does not automate comment replies.',
  },
  {
    q: 'Who controls what the AI says?',
    a: 'Each business controls its approved company information. Replies use that published content for that business only.',
  },
  {
    q: 'Which Meta accounts can I connect?',
    a: 'Only Facebook Pages and Instagram Professional Accounts your business owns or is authorized to manage.',
  },
  {
    q: 'Is WhatsApp used as an inbound AI channel?',
    a: 'No. WhatsApp may be used as an outbound handoff destination when a customer asks for booking or human help. Inbound WhatsApp messages do not enter the AI.',
  },
  {
    q: 'How do I request data deletion?',
    a: 'Use the Data Deletion instructions page, remove the app through Meta settings, or email the contact address published on that page.',
  },
];

const Landing = () => {
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-sky-50 to-fuchsia-50 text-slate-900">
      <div className="pointer-events-none fixed inset-0 overflow-hidden" aria-hidden="true">
        <div className="absolute -right-40 -top-40 h-80 w-80 rounded-full bg-primary-200/70 blur-3xl" />
        <div className="absolute -bottom-40 -left-40 h-80 w-80 rounded-full bg-secondary-200/70 blur-3xl" />
      </div>

      <PublicSiteHeader />

      <main>
        <section className="relative mx-auto grid max-w-6xl gap-10 px-4 pb-16 pt-12 sm:px-6 lg:grid-cols-[1.15fr_0.85fr] lg:items-center lg:pb-24 lg:pt-20">
          <div>
            <p className="font-display text-sm font-semibold uppercase tracking-[0.18em] text-primary-700">
              {PUBLIC_SITE.productName}
            </p>
            <h1 className="mt-4 max-w-xl font-display text-4xl font-bold leading-tight text-slate-950 sm:text-5xl lg:text-6xl">
              {PUBLIC_SITE.heroTitle}
            </h1>
            <p className="mt-5 max-w-xl text-lg leading-relaxed text-slate-700">
              {PUBLIC_SITE.heroSupport}
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Link
                to={PUBLIC_PATHS.register}
                className="rounded-xl bg-gradient-to-r from-primary-600 to-secondary-600 px-5 py-3 text-base font-semibold text-white shadow-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-primary-500"
              >
                Create Account
              </Link>
              <Link
                to={PUBLIC_PATHS.login}
                className="rounded-xl border border-slate-300 bg-white/80 px-5 py-3 text-base font-semibold text-slate-800 hover:bg-white focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
              >
                Log in
              </Link>
            </div>
          </div>

          <motion.div
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.45 }}
            className="relative overflow-hidden rounded-3xl border border-white/70 bg-slate-950 text-white shadow-2xl"
            aria-hidden="true"
          >
            <div className="absolute inset-0 bg-gradient-to-br from-primary-700/40 via-slate-950 to-secondary-700/30" />
            <div className="relative space-y-5 p-6 sm:p-8">
              <div className="flex items-center gap-3">
                <span className="inline-flex h-11 w-11 items-center justify-center rounded-2xl bg-white/10">
                  <SparklesIcon className="h-6 w-6" />
                </span>
                <div>
                  <p className="font-display text-lg font-semibold">{PUBLIC_SITE.productName}</p>
                  <p className="text-sm text-white/70">Messenger & Instagram private messages</p>
                </div>
              </div>
              <div className="space-y-3 text-sm leading-relaxed text-white/90">
                <p className="rounded-2xl bg-white/10 px-4 py-3">Customer: “What are your hours this week?”</p>
                <p className="rounded-2xl bg-primary-500/30 px-4 py-3">
                  AI reply uses only the business-approved hours and branch details published by that company.
                </p>
                <p className="rounded-2xl bg-white/10 px-4 py-3">
                  Need a person? Route to the company’s chosen contact channel — never invent bookings inside Meta.
                </p>
              </div>
            </div>
          </motion.div>
        </section>

        <section id="how-it-works" className="border-y border-slate-200/70 bg-white/60 py-16">
          <div className="mx-auto max-w-6xl px-4 sm:px-6">
            <h2 className="font-display text-3xl font-bold text-slate-950">How It Works</h2>
            <p className="mt-3 max-w-2xl text-slate-600">
              From account creation to private-message replies, each business stays in control of its Meta assets and approved information.
            </p>
            <ol className="mt-10 grid gap-6 md:grid-cols-2">
              {steps.map((step, index) => (
                <li key={step.title} className="rounded-2xl border border-slate-200 bg-white/90 p-6 shadow-sm">
                  <p className="text-sm font-semibold uppercase tracking-wide text-primary-700">Step {index + 1}</p>
                  <h3 className="mt-2 font-display text-xl font-semibold text-slate-900">{step.title}</h3>
                  <p className="mt-2 text-slate-600">{step.body}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section id="features" className="py-16">
          <div className="mx-auto max-w-6xl px-4 sm:px-6">
            <h2 className="font-display text-3xl font-bold text-slate-950">Features</h2>
            <p className="mt-3 max-w-2xl text-slate-600">
              Built for private customer messaging on Facebook and Instagram — not ads, comments, or public publishing.
            </p>
            <div className="mt-10 grid gap-6 md:grid-cols-2">
              {features.map((feature) => {
                const Icon = feature.icon;
                return (
                  <article key={feature.title} className="rounded-2xl border border-slate-200/80 bg-white/80 p-6">
                    <Icon className="h-7 w-7 text-primary-600" aria-hidden="true" />
                    <h3 className="mt-4 font-display text-xl font-semibold">{feature.title}</h3>
                    <p className="mt-2 text-slate-600">{feature.body}</p>
                  </article>
                );
              })}
            </div>
          </div>
        </section>

        <section id="meta-connection" className="border-y border-slate-200/70 bg-white/70 py-16">
          <div className="mx-auto max-w-6xl px-4 sm:px-6">
            <h2 className="font-display text-3xl font-bold text-slate-950">Facebook & Instagram Connection</h2>
            <p className="mt-3 max-w-3xl text-slate-600">
              After you create an account, connect the Facebook Page and Instagram Professional Account your business
              owns or is authorized to manage. Connection uses Meta Business Login. You can disconnect those accounts
              from the dashboard when you no longer want Linas AI to receive or reply to their private messages.
            </p>
          </div>
        </section>

        <section id="training" className="py-16">
          <div className="mx-auto max-w-6xl px-4 sm:px-6">
            <h2 className="font-display text-3xl font-bold text-slate-950">Business-Controlled AI Training</h2>
            <p className="mt-3 max-w-3xl text-slate-600">
              Add company information, services, prices, branches, hours, and FAQs. Publish the content your team
              approves. Linas AI uses that published information for your tenant only — it does not share one business’s
              content with another.
            </p>
            <ul className="mt-6 space-y-3 text-slate-700">
              {[
                'Create a company account with an isolated workspace',
                'Connect authorized Facebook Page and Instagram Professional accounts',
                'Add and publish approved business information',
                'Auto-reply to Instagram private messages and Facebook Messenger',
                'Route booking or human help to your chosen contact channel',
                'Disconnect Meta accounts or request data deletion',
              ].map((item) => (
                <li key={item} className="flex items-start gap-3">
                  <CheckBadgeIcon className="mt-0.5 h-5 w-5 shrink-0 text-secondary-600" aria-hidden="true" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section id="privacy" className="border-y border-slate-200/70 bg-white/70 py-16">
          <div className="mx-auto max-w-6xl px-4 sm:px-6">
            <h2 className="font-display text-3xl font-bold text-slate-950">Privacy and Data Use</h2>
            <p className="mt-4 max-w-4xl text-base leading-relaxed text-slate-700">
              {PUBLIC_SITE.metaPlatformDataUse}
            </p>
            <p className="mt-4 text-sm text-slate-600">
              Read the full{' '}
              <a className="font-semibold text-primary-700 underline" href={PUBLIC_PATHS.privacy}>
                Privacy Policy
              </a>
              ,{' '}
              <a className="font-semibold text-primary-700 underline" href={PUBLIC_PATHS.terms}>
                Terms of Service
              </a>
              , and{' '}
              <a className="font-semibold text-primary-700 underline" href={PUBLIC_PATHS.dataDeletion}>
                User Data Deletion Instructions
              </a>
              .
            </p>
          </div>
        </section>

        <section id="faq" className="py-16">
          <div className="mx-auto max-w-6xl px-4 sm:px-6">
            <h2 className="font-display text-3xl font-bold text-slate-950">Frequently Asked Questions</h2>
            <div className="mt-8 space-y-4">
              {faqs.map((item) => (
                <details key={item.q} className="group rounded-2xl border border-slate-200 bg-white/90 p-5 open:shadow-sm">
                  <summary className="cursor-pointer list-none font-semibold text-slate-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 rounded">
                    {item.q}
                  </summary>
                  <p className="mt-3 text-slate-600">{item.a}</p>
                </details>
              ))}
            </div>
          </div>
        </section>

        <section id="about-provider" className="border-y border-slate-200/70 bg-white/70 py-16">
          <div className="mx-auto max-w-6xl px-4 sm:px-6">
            <h2 className="font-display text-3xl font-bold text-slate-950">About the Provider</h2>
            <p className="mt-3 max-w-3xl text-slate-600">
              {PUBLIC_SITE.productName} is the software platform behind{' '}
              <a className="font-semibold text-primary-700 underline" href={PUBLIC_SITE.publicBaseUrl}>
                {PUBLIC_SITE.publicBaseUrl.replace('https://', '')}
              </a>
              . It helps businesses answer private Facebook Messenger and Instagram customer messages using information
              each business approves and controls.
            </p>
            <p className="mt-4">
              <Link className="font-semibold text-primary-700 underline" to={PUBLIC_PATHS.about}>
                More about {PUBLIC_SITE.productName}
              </Link>
            </p>
          </div>
        </section>

        <section id="contact" className="py-16">
          <div className="mx-auto max-w-6xl px-4 sm:px-6">
            <h2 className="font-display text-3xl font-bold text-slate-950">Contact</h2>
            <p className="mt-3 max-w-2xl text-slate-600">
              For product, privacy, or data-deletion questions, email{' '}
              <a className="font-semibold text-primary-700 underline" href={`mailto:${PUBLIC_SITE.contactEmail}`}>
                {PUBLIC_SITE.contactEmail}
              </a>
              .
            </p>
            <p className="mt-4">
              <Link className="font-semibold text-primary-700 underline" to={PUBLIC_PATHS.contact}>
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
