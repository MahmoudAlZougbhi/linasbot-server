import type { BillingPeriod } from './appleProductIds';
import {
  APPLE_CREDIT_PRODUCTS,
  CREDIT_PACK_ORDER,
  allAppleCreditProductIds,
  allAppleSubscriptionProductIds,
  appleProductIdForPlan,
  type CreditPackId,
} from './appleProductIds';
import { loadIapModule } from './iapNative';
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

export type CreditStorePrice = {
  credits: CreditPackId;
  productId: string;
  localizedPrice: string;
  currencyCode: string;
  available: boolean;
};

export type StorePricingState = {
  loading: boolean;
  error: string | null;
  prices: Record<PlanId, StorePrice | null>;
  creditPrices: CreditStorePrice[];
  platform: 'apple' | 'google' | 'unknown';
  period: BillingPeriod;
};

function emptyPlanPrices(period: BillingPeriod, store: 'apple' | 'google' | 'unknown') {
  const prices = {} as Record<PlanId, StorePrice | null>;
  for (const id of PLAN_ORDER) {
    const def = PLAN_CATALOG[id];
    prices[id] = {
      planId: id,
      productId:
        store === 'apple' ? appleProductIdForPlan(id, period) : def.googleProductId,
      localizedPrice: '',
      currencyCode: '',
      available: false,
      preview: false,
    };
  }
  return prices;
}

function emptyCreditPrices(): CreditStorePrice[] {
  return CREDIT_PACK_ORDER.map((credits) => ({
    credits,
    productId: APPLE_CREDIT_PRODUCTS[credits],
    localizedPrice: '',
    currencyCode: '',
    available: false,
  }));
}

/**
 * Load StoreKit localized displayPrice strings. Never invent checkout prices.
 * Android / web / Expo Go → available:false with a clear error code.
 */
export async function loadStorePrices(
  platform: 'ios' | 'android' | 'web' | string = 'unknown',
  period: BillingPeriod = 'monthly',
): Promise<StorePricingState> {
  const store: 'apple' | 'google' | 'unknown' =
    platform === 'ios' ? 'apple' : platform === 'android' ? 'google' : 'unknown';

  const base: StorePricingState = {
    loading: false,
    error: null,
    prices: emptyPlanPrices(period, store),
    creditPrices: emptyCreditPrices(),
    platform: store,
    period,
  };

  if (platform !== 'ios') {
    return { ...base, error: store === 'google' ? 'android_iap_not_enabled' : 'store_unavailable' };
  }

  const iap = loadIapModule();
  if (!iap) {
    return { ...base, error: 'native_iap_unavailable' };
  }

  try {
    await iap.initConnection();
    const subSkus = allAppleSubscriptionProductIds();
    const creditSkus = allAppleCreditProductIds();
    const [subs, products] = await Promise.all([
      iap.fetchProducts({ skus: subSkus, type: 'subs' }),
      iap.fetchProducts({ skus: creditSkus, type: 'in-app' }),
    ]);

    const byId = new Map<string, { displayPrice?: string; currency?: string }>();
    for (const p of [...(subs ?? []), ...(products ?? [])]) {
      if (p && typeof p === 'object' && 'id' in p) {
        const row = p as { id: string; displayPrice?: string; currency?: string };
        byId.set(row.id, row);
      }
    }

    const prices = emptyPlanPrices(period, 'apple');
    for (const id of PLAN_ORDER) {
      const productId = appleProductIdForPlan(id, period);
      const hit = byId.get(productId);
      if (hit?.displayPrice) {
        prices[id] = {
          planId: id,
          productId,
          localizedPrice: hit.displayPrice,
          currencyCode: hit.currency ?? '',
          available: true,
          preview: false,
        };
      } else {
        prices[id] = {
          planId: id,
          productId,
          localizedPrice: '',
          currencyCode: '',
          available: false,
          preview: false,
        };
      }
    }

    const creditPrices = CREDIT_PACK_ORDER.map((credits) => {
      const productId = APPLE_CREDIT_PRODUCTS[credits];
      const hit = byId.get(productId);
      return {
        credits,
        productId,
        localizedPrice: hit?.displayPrice ?? '',
        currencyCode: hit?.currency ?? '',
        available: Boolean(hit?.displayPrice),
      };
    });

    const anyAvailable =
      PLAN_ORDER.some((id) => prices[id]?.available) || creditPrices.some((c) => c.available);

    return {
      loading: false,
      error: anyAvailable ? null : 'products_not_found',
      prices,
      creditPrices,
      platform: 'apple',
      period,
    };
  } catch (err) {
    return {
      ...base,
      error: err instanceof Error ? err.message : 'store_load_failed',
    };
  }
}

/** Dev-only preview markers — never enable purchase / never use for CTA checkout label. */
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
      productId: appleProductIdForPlan(id, 'monthly'),
      localizedPrice: formatted,
      currencyCode: 'USD',
      available: false,
      preview: true,
    };
  }
  return out;
}
