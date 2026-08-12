import { useCallback, useEffect, useState } from 'react';
import { Platform } from 'react-native';
import { z } from 'zod';

import { apiFetch } from '../../api/client';
import { useI18n } from '../../i18n/LanguageContext';
import type { BillingPeriod } from './appleProductIds';
import { isPlanId, type PlanId } from './planCatalog';
import {
  loadStorePrices,
  previewCatalogPrices,
  type CreditStorePrice,
  type StorePrice,
} from './storePricing';

const EntitlementsSchema = z.object({ success: z.boolean() }).passthrough();
const UsageSchema = z.object({ success: z.literal(true) }).passthrough();

export type BillingEntitlementState = {
  loading: boolean;
  error: string | null;
  planId: PlanId | null;
  status: string | null;
  periodEnd: number | null;
  includedCredits: number | null;
  purchasedCredits: number | null;
  creditBalance: number | null;
  raw: string;
};

export function useBillingEntitlement() {
  const { tr } = useI18n();
  const [state, setState] = useState<BillingEntitlementState>({
    loading: true,
    error: null,
    planId: null,
    status: null,
    periodEnd: null,
    includedCredits: null,
    purchasedCredits: null,
    creditBalance: null,
    raw: '',
  });

  const refresh = useCallback(async () => {
    setState((s) => ({ ...s, loading: true }));
    try {
      const data = await apiFetch('/api/entitlements/me', { schema: EntitlementsSchema });
      const record = data as Record<string, unknown>;
      const entitlement =
        record.entitlement && typeof record.entitlement === 'object'
          ? (record.entitlement as Record<string, unknown>)
          : record;
      const p =
        (typeof entitlement.plan_id === 'string' && entitlement.plan_id) ||
        (typeof entitlement.plan === 'string' && entitlement.plan) ||
        null;
      const purchased =
        typeof entitlement.purchased_credits === 'number'
          ? entitlement.purchased_credits
          : typeof entitlement.extra_credits === 'number'
            ? entitlement.extra_credits
            : null;
      let creditBalance: number | null = null;
      try {
        const res = await apiFetch('/api/mobile/usage', { schema: UsageSchema });
        const bal = (res as Record<string, unknown>).credit_balance;
        creditBalance = typeof bal === 'number' ? bal : null;
      } catch {
        creditBalance = null;
      }
      setState({
        loading: false,
        error: null,
        planId: isPlanId(p) ? p : null,
        status: typeof entitlement.status === 'string' ? entitlement.status : null,
        periodEnd:
          typeof entitlement.current_period_end === 'number'
            ? entitlement.current_period_end
            : null,
        includedCredits:
          typeof entitlement.included_credits === 'number'
            ? entitlement.included_credits
            : null,
        purchasedCredits: purchased,
        creditBalance,
        raw: __DEV__ ? JSON.stringify(data, null, 2) : '',
      });
    } catch {
      setState({
        loading: false,
        error: tr('subLoadError'),
        planId: null,
        status: null,
        periodEnd: null,
        includedCredits: null,
        purchasedCredits: null,
        creditBalance: null,
        raw: '',
      });
    }
  }, [tr]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { ...state, refresh };
}

export function useBillingStorePrices(period: BillingPeriod, locale: string) {
  const { tr } = useI18n();
  const [storeLoading, setStoreLoading] = useState(false);
  const [storePrices, setStorePrices] = useState<Record<PlanId, StorePrice | null>>({
    lite: null,
    starter: null,
    growth: null,
    pro: null,
    max: null,
  });
  const [creditPrices, setCreditPrices] = useState<CreditStorePrice[]>([]);
  const [purchaseNote, setPurchaseNote] = useState<string | null>(null);

  const refreshStore = useCallback(async () => {
    setStoreLoading(true);
    try {
      const state = await loadStorePrices(Platform.OS, period);
      setStorePrices(state.prices);
      setCreditPrices(state.creditPrices);
      if (state.error === 'native_iap_unavailable' || state.error === 'store_unavailable') {
        if (__DEV__) {
          setStorePrices(previewCatalogPrices(locale));
          setPurchaseNote(tr('subPricePreview'));
        } else {
          setPurchaseNote(tr('subStoreUnavailable'));
        }
      } else if (state.error) {
        setPurchaseNote(tr('subStoreUnavailable'));
      } else {
        setPurchaseNote(null);
      }
    } finally {
      setStoreLoading(false);
    }
  }, [locale, period, tr]);

  useEffect(() => {
    void refreshStore();
  }, [refreshStore]);

  return {
    storeLoading,
    storePrices,
    creditPrices,
    purchaseNote,
    setPurchaseNote,
    refreshStore,
  };
}
