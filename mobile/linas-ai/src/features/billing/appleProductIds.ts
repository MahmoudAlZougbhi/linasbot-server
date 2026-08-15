import type { PlanId } from './planCatalog';
import { PLAN_ORDER } from './planCatalog';

export type BillingPeriod = 'monthly' | 'yearly';

export type CreditPackId = 2500 | 5000 | 12500 | 25000 | 50000;

/** ASC auto-renewable subscription product IDs (canonical). */
export const APPLE_SUBSCRIPTION_PRODUCTS: Record<
  PlanId,
  { monthly: string; yearly: string }
> = {
  lite: {
    monthly: 'com.linasai.subscription.basic.monthly',
    yearly: 'com.linasai.subscription.basic.yearly',
  },
  starter: {
    monthly: 'com.linasai.subscription.plus.monthly',
    yearly: 'com.linasai.subscription.plus.yearly',
  },
  growth: {
    monthly: 'com.linasai.subscription.growth.monthly',
    yearly: 'com.linasai.subscription.growth.yearly',
  },
  pro: {
    monthly: 'com.linasai.subscription.pro.monthly',
    yearly: 'com.linasai.subscription.pro.yearly',
  },
  max: {
    monthly: 'com.linasai.subscription.scale.monthly',
    yearly: 'com.linasai.subscription.scale.yearly',
  },
};

export const APPLE_CREDIT_PRODUCTS: Record<CreditPackId, string> = {
  2500: 'com.linasai.credits.2500',
  5000: 'com.linasai.credits.5000',
  12500: 'com.linasai.credits.12500',
  25000: 'com.linasai.credits.25000',
  50000: 'com.linasai.credits.50000',
};

export const CREDIT_PACK_ORDER: CreditPackId[] = [2500, 5000, 12500, 25000, 50000];

/** Catalog USD for display only — checkout must use store-localized price. */
export const CREDIT_PACK_CATALOG_USD: Record<CreditPackId, number> = {
  2500: 4.99,
  5000: 9.99,
  12500: 24.99,
  25000: 49.99,
  50000: 99.99,
};

export const DEFAULT_CREDIT_PACK: CreditPackId = 5000;

export function appleProductIdForPlan(planId: PlanId, period: BillingPeriod): string {
  return APPLE_SUBSCRIPTION_PRODUCTS[planId][period];
}

export function planIdForAppleProduct(productId: string): PlanId | null {
  for (const id of PLAN_ORDER) {
    const row = APPLE_SUBSCRIPTION_PRODUCTS[id];
    if (row.monthly === productId || row.yearly === productId) return id;
  }
  return null;
}

export function periodForAppleProduct(productId: string): BillingPeriod | null {
  for (const id of PLAN_ORDER) {
    const row = APPLE_SUBSCRIPTION_PRODUCTS[id];
    if (row.monthly === productId) return 'monthly';
    if (row.yearly === productId) return 'yearly';
  }
  return null;
}

export function creditAmountForAppleProduct(productId: string): CreditPackId | null {
  for (const amount of CREDIT_PACK_ORDER) {
    if (APPLE_CREDIT_PRODUCTS[amount] === productId) return amount;
  }
  return null;
}

export function allAppleSubscriptionProductIds(): string[] {
  const out: string[] = [];
  for (const id of PLAN_ORDER) {
    out.push(APPLE_SUBSCRIPTION_PRODUCTS[id].monthly, APPLE_SUBSCRIPTION_PRODUCTS[id].yearly);
  }
  return out;
}

export function allAppleCreditProductIds(): string[] {
  return CREDIT_PACK_ORDER.map((n) => APPLE_CREDIT_PRODUCTS[n]);
}

export function isAppleSubscriptionProduct(productId: string): boolean {
  return planIdForAppleProduct(productId) != null;
}

export function isAppleCreditProduct(productId: string): boolean {
  return creditAmountForAppleProduct(productId) != null;
}
