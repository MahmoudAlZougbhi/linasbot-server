import { scopedCacheKey } from './sessionScope';

export const queryKeys = {
  dashboard: (periodKey: string, tz: string) => scopedCacheKey(['dashboard', periodKey, tz]),
  users: () => scopedCacheKey(['users']),
  roles: () => scopedCacheKey(['roles']),
  products: () => scopedCacheKey(['products']),
  integrations: () => scopedCacheKey(['integrations']),
  requests: (suffix: string) => scopedCacheKey(['requests', suffix]),
  settingsProfile: () => scopedCacheKey(['settings', 'profile']),
  cmHub: () => scopedCacheKey(['cm', 'hub']),
  cmDraft: () => scopedCacheKey(['cmDraft']),
  liveChatInbox: (filter: string, channel: string, search: string) =>
    scopedCacheKey(['livechat', 'inbox', filter, channel, search]),
  commentsInbox: (platform: string) => scopedCacheKey(['comments', 'inbox', platform]),
  notifications: () => scopedCacheKey(['notifications']),
  faq: (q: string) => scopedCacheKey(['faq', q]),
  faqAll: () => scopedCacheKey(['faq']),
  smartFollowUp: () => scopedCacheKey(['smartFollowUp']),
  billing: () => scopedCacheKey(['billing']),
};
