/** Stale-while-revalidate TTLs. Cached rows stay on screen after TTL; TTL only gates refetch. */

export const QUERY_TTL = {
  dashboard: 30_000,
  users: 90_000,
  roles: 90_000,
  products: 90_000,
  services: 90_000,
  integrations: 45_000,
  requests: 20_000,
  settings: 5 * 60_000,
  cmHub: 45_000,
  cmDraft: 60_000,
  liveChatInbox: 8_000,
  liveChatThread: 15_000,
  commentsInbox: 8_000,
  notifications: 20_000,
  faq: 90_000,
  smartFollowUp: 5 * 60_000,
} as const;

export const QUERY_CACHE_MAX_ENTRIES = 40;
