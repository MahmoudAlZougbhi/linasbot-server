/** Shared public-site facts — only values already used in repo compliance pages. */
export const PUBLIC_SITE = {
  productName: 'Linas AI',
  publicBaseUrl: 'https://www.linasaibot.com',
  contactEmail: 'Mahmoudalzougbhi@gmail.com',
  heroTitle: 'Linas AI',
  heroHeadline: 'Turn every DM and comment into a helpful answer.',
  heroSupport:
    'Linas AI answers customers using business facts you approve—while one chat-first Owner Copilot keeps setup, control, and visibility in your hands. This site is marketing + a short guest chat. Day-to-day work happens in the app.',
  metaPlatformDataUse:
    'Our business provides a software platform that helps businesses respond to customer inquiries received on their Facebook Pages and Instagram professional accounts. With each client’s permission, we use the account details and customer messages provided by Meta only to receive inquiries, send automated replies using information approved by the client, and direct customers to the client’s chosen contact channel when booking or human assistance is needed. Each client connects only business accounts it owns or is authorized to manage.',
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
