import type { PlanId } from './planCatalog';
import { PLAN_CATALOG, PLAN_ORDER } from './planCatalog';

export type StorePrice = {
  planId: PlanId;
  productId: string;
  localizedPrice: string;
  currencyCode: string;
  available: boolean;
  preview?: boolean;
};

export type StorePricingState = {
  loading: boolean;
  error: string | null;
  prices: Record<PlanId, StorePrice | null>;
  platform: 'apple' | 'google' | 'unknown';
};

/**
 * StoreKit / Play Billing are not bound in this app binary yet.
 * Never invent a purchaseable price — return unavailable until IAP credentials and products exist.
 */
export async function loadStorePrices(
  platform: 'ios' | 'android' | 'web' | string = 'unknown',
): Promise<StorePricingState> {
  const store: 'apple' | 'google' | 'unknown' =
    platform === 'ios' ? 'apple' : platform === 'android' ? 'google' : 'unknown';

  const prices = {} as Record<PlanId, StorePrice | null>;
  for (const id of PLAN_ORDER) {
    const def = PLAN_CATALOG[id];
    prices[id] = {
      planId: id,
      productId: store === 'apple' ? def.appleProductId : def.googleProductId,
      localizedPrice: '',
      currencyCode: '',
      available: false,
      preview: false,
    };
  }

  return {
    loading: false,
    error: 'store_unavailable',
    prices,
    platform: store,
  };
}

/** Dev-only preview markers — never enable purchase. */
export function previewCatalogPrices(locale: string): Record<PlanId, StorePrice> {
  const out = {} as Record<PlanId, StorePrice>;
  for (const id of PLAN_ORDER) {
    const def = PLAN_CATALOG[id];
    const formatted = new Intl.NumberFormat(locale || 'en', {
      style: 'currency',
      currency: 'USD',
      maximumFractionDigits: def.catalogPriceUsd % 1 === 0 ? 0 : 2,
    }).format(def.catalogPriceUsd);
    out[id] = {
      planId: id,
      productId: def.appleProductId,
      localizedPrice: formatted,
      currencyCode: 'USD',
      available: false,
      preview: true,
    };
  }
  return out;
}
