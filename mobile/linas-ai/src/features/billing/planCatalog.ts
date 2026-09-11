/**
 * Frozen membership-v1 plan matrix — must match services.membership.plan_catalog.
 * Baseline USD is catalog reference only; checkout must use store-localized price.
 */
export type PlanId = 'lite' | 'starter' | 'growth' | 'pro' | 'max';

export type PlanDefinition = {
  id: PlanId;
  /** Catalog baseline USD/month (never used as active checkout fallback). */
  catalogPriceUsd: number;
  includedCredits: number;
  includedMessages: number;
  faqCapacity: number;
  /** null = unlimited additional members (owner excluded). */
  additionalSeats: number | null;
  commentAutomation: boolean;
  /** WhatsApp messages — Lite excluded; Starter and above included. */
  whatsapp: boolean;
  /** TikTok DMs + comments — Growth, Pro, and Max. */
  tiktok: boolean;
  /** Website chat widget — Lite excluded; Starter and above included. */
  web: boolean;
  recommended?: boolean;
  /**
   * Default Apple monthly product id (canonical ASC SKU).
   * Yearly variants live in appleProductIds.ts — server map is authoritative.
   */
  appleProductId: string;
  googleProductId: string;
};

export const PLAN_ORDER: PlanId[] = ['lite', 'starter', 'growth', 'pro', 'max'];

export const PLAN_CATALOG: Record<PlanId, PlanDefinition> = {
  lite: {
    id: 'lite',
    catalogPriceUsd: 10,
    includedCredits: 7000,
    includedMessages: 550,
    faqCapacity: 50,
    additionalSeats: 0,
    commentAutomation: false,
    whatsapp: false,
    tiktok: false,
    web: false,
    appleProductId: 'com.linasai.subscription.basic.monthly',
    googleProductId: 'linas_ai_lite_monthly',
  },
  starter: {
    id: 'starter',
    catalogPriceUsd: 29,
    includedCredits: 17500,
    includedMessages: 1200,
    faqCapacity: 110,
    additionalSeats: 2,
    commentAutomation: true,
    whatsapp: true,
    tiktok: false,
    web: true,
    appleProductId: 'com.linasai.subscription.plus.monthly',
    googleProductId: 'linas_ai_starter_monthly',
  },
  growth: {
    id: 'growth',
    catalogPriceUsd: 59,
    includedCredits: 41300,
    includedMessages: 3000,
    faqCapacity: 250,
    additionalSeats: 5,
    commentAutomation: true,
    whatsapp: true,
    tiktok: true,
    web: true,
    recommended: true,
    appleProductId: 'com.linasai.subscription.growth.monthly',
    googleProductId: 'linas_ai_growth_monthly',
  },
  pro: {
    id: 'pro',
    catalogPriceUsd: 120,
    includedCredits: 76300,
    includedMessages: 10000,
    faqCapacity: 600,
    additionalSeats: null,
    commentAutomation: true,
    whatsapp: true,
    tiktok: true,
    web: true,
    appleProductId: 'com.linasai.subscription.pro.monthly',
    googleProductId: 'linas_ai_pro_monthly',
  },
  max: {
    id: 'max',
    catalogPriceUsd: 279,
    includedCredits: 181300,
    includedMessages: 25000,
    faqCapacity: 1500,
    additionalSeats: null,
    commentAutomation: true,
    whatsapp: true,
    tiktok: true,
    web: true,
    appleProductId: 'com.linasai.subscription.scale.monthly',
    googleProductId: 'linas_ai_max_monthly',
  },
};

export const COMMON_FEATURE_KEYS = [
  'subCommonOwnerCopilot',
  'subCommonContentManagement',
  'subCommonAiReplies',
  'subCommonIgDm',
  'subCommonFbDm',
  'subCommonAnalytics',
  'subCommonIntegrations',
] as const;

export function isPlanId(value: string | null | undefined): value is PlanId {
  return Boolean(value && value in PLAN_CATALOG);
}

/** Overlay server catalog numbers. IAP product IDs stay local. */
export function applyPublicPlans(rows: Array<Record<string, unknown>>): void {
  for (const row of rows) {
    const id = String(row.plan_id || '');
    if (!isPlanId(id)) continue;
    const current = PLAN_CATALOG[id];
    const price = Number(row.intended_price_usd ?? row.price_usd);
    const messages = Number(row.included_messages);
    const faq = Number(row.faq_capacity);
    if (Number.isFinite(price) && price > 0) current.catalogPriceUsd = price;
    if (Number.isFinite(messages) && messages > 0) current.includedMessages = messages;
    if (Number.isFinite(faq) && faq >= 0) current.faqCapacity = faq;
    if (typeof row.comment_automation === 'boolean') current.commentAutomation = row.comment_automation;
    if (typeof row.whatsapp === 'boolean') current.whatsapp = row.whatsapp;
    if (typeof row.web === 'boolean') current.web = row.web;
    if (typeof row.tiktok === 'boolean') current.tiktok = row.tiktok;
    if (row.additional_seats === null || row.additional_seats_unlimited === true) {
      current.additionalSeats = null;
    } else if (Number.isFinite(Number(row.additional_seats))) {
      current.additionalSeats = Number(row.additional_seats);
    }
  }
}

export const HIGHEST_PLAN_ID: PlanId = 'max';

export function isHighestPlan(id: string | null | undefined): boolean {
  return (id || '').trim().toLowerCase() === HIGHEST_PLAN_ID;
}

export function planRank(id: PlanId): number {
  return PLAN_ORDER.indexOf(id);
}

export function isLowestPlan(id: string | null | undefined): boolean {
  const rank = PLAN_ORDER.indexOf((id || '').trim().toLowerCase() as PlanId);
  return rank === 0;
}

export function plansBelow(current: PlanId): PlanId[] {
  const rank = planRank(current);
  if (rank <= 0) return [];
  return PLAN_ORDER.slice(0, rank);
}
