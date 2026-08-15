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
  faqCapacity: number;
  /** null = unlimited additional members (owner excluded). */
  additionalSeats: number | null;
  commentAutomation: boolean;
  /** WhatsApp messages — Lite excluded; Starter and above included. */
  whatsapp: boolean;
  /** TikTok DMs + comments — Growth, Pro, and Max. */
  tiktok: boolean;
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
    catalogPriceUsd: 9.99,
    includedCredits: 7000,
    faqCapacity: 50,
    additionalSeats: 0,
    commentAutomation: false,
    whatsapp: false,
    tiktok: false,
    appleProductId: 'com.linasai.subscription.basic.monthly',
    googleProductId: 'linas_ai_lite_monthly',
  },
  starter: {
    id: 'starter',
    catalogPriceUsd: 25,
    includedCredits: 17500,
    faqCapacity: 110,
    additionalSeats: 2,
    commentAutomation: true,
    whatsapp: true,
    tiktok: false,
    appleProductId: 'com.linasai.subscription.plus.monthly',
    googleProductId: 'linas_ai_starter_monthly',
  },
  growth: {
    id: 'growth',
    catalogPriceUsd: 59,
    includedCredits: 41300,
    faqCapacity: 250,
    additionalSeats: 5,
    commentAutomation: true,
    whatsapp: true,
    tiktok: true,
    recommended: true,
    appleProductId: 'com.linasai.subscription.growth.monthly',
    googleProductId: 'linas_ai_growth_monthly',
  },
  pro: {
    id: 'pro',
    catalogPriceUsd: 109,
    includedCredits: 76300,
    faqCapacity: 600,
    additionalSeats: null,
    commentAutomation: true,
    whatsapp: true,
    tiktok: true,
    appleProductId: 'com.linasai.subscription.pro.monthly',
    googleProductId: 'linas_ai_pro_monthly',
  },
  max: {
    id: 'max',
    catalogPriceUsd: 259,
    includedCredits: 181300,
    faqCapacity: 1500,
    additionalSeats: null,
    commentAutomation: true,
    whatsapp: true,
    tiktok: true,
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

export const HIGHEST_PLAN_ID: PlanId = 'max';

export function isHighestPlan(id: string | null | undefined): boolean {
  return (id || '').trim().toLowerCase() === HIGHEST_PLAN_ID;
}

export function planRank(id: PlanId): number {
  return PLAN_ORDER.indexOf(id);
}
