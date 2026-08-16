/** Shared public-site facts — only values already used in repo compliance pages. */
export const PUBLIC_SITE = {
  productName: 'Linas AI',
  publicBaseUrl: 'https://www.linasaibot.com',
  contactEmail: 'support@linasai.com',
  heroTitle: 'Linas AI',
  heroHeadline: 'Talk to Linas. Linas talks to your customers.',
  heroKicker: 'AI customer care, trained by you',
  heroSupport:
    'Teach Linas about your business once. It replies across every connected channel—while you stay in control.',
  metaPlatformDataUse:
    'Linas AI is a business customer-support platform that helps companies answer customers using knowledge each business approves. With each client’s permission, we may process inquiries on Facebook, Instagram, WhatsApp, and TikTok when that client connects those accounts through official platform integrations. We use account details and customer messages from those platforms only to receive inquiries, send automated replies from approved business knowledge, support Owner chat and AI Setup for that client, and direct customers to the client’s chosen contact channel when booking or human assistance is needed. Each client connects only business accounts it owns or is authorized to manage.',
};

/**
 * Store listing status — do not invent App Store / Play IDs.
 * Update `url` when ASC / Play Console listings are live.
 */
export const STORE_LINKS = {
  appStore: {
    label: 'Download on the App Store',
    status: 'pending',
    /** Set to full https://apps.apple.com/app/id… when ASC listing is public. */
    url: null,
    blocker:
      'No public App Store URL or numeric Apple ID is committed in-repo yet (TestFlight / ASC gate still pending).',
  },
  playStore: {
    label: 'Get it on Google Play',
    status: 'pending',
    /** Set to https://play.google.com/store/apps/details?id=com.linasai.app when live. */
    url: null,
    packageName: 'com.linasai.app',
    blocker: 'Google Play listing for com.linasai.app is not live yet.',
  },
};

export const PUBLIC_PATHS = {
  home: '/',
  register: '/register',
  login: '/login',
  forgotPassword: '/forgot-password',
  resetPassword: '/reset-password',
  verifyEmail: '/verify-email',
  about: '/about',
  contact: '/contact',
  pricing: '/pricing',
  features: '/features',
  privacy: '/privacy-policy',
  terms: '/terms',
  dataDeletion: '/data-deletion',
  appHome: '/app',
  wallet: '/wallet',
  getApp: '/#get-app',
  guestChat: '/#talk-to-linas',
};
