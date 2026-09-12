import { useCallback, useEffect, useState } from 'react';
import { Platform } from 'react-native';
import { z } from 'zod';

import { apiFetch } from '../../api/client';
import { cacheGet, cacheSet } from '../../cache/queryCache';
import { queryKeys } from '../../cache/queryKeys';
import { splitCreditRemaining } from '../dashboard/creditSplit';
import { useI18n } from '../../i18n/LanguageContext';
import type { BillingPeriod } from './appleProductIds';
import { applyPublicPlans, isPlanId, type PlanId } from './planCatalog';
import { parsePendingDowngrade, type PendingDowngrade } from './planChangeApi';
import {
  loadStorePrices,
  previewCatalogPrices,
  type CreditStorePrice,
  type StorePrice,
} from './storePricing';

const EntitlementsSchema = z.object({ success: z.boolean() }).passthrough();
const UsageSchema = z.object({ success: z.literal(true) }).passthrough();

function asNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

export type BillingEntitlementState = {
  loading: boolean;
  error: string | null;
  planId: PlanId | null;
  status: string | null;
  periodEnd: number | null;
  includedCredits: number | null;
  purchasedCredits: number | null;
  creditBalance: number | null;
  membershipRemaining: number | null;
  boughtRemaining: number | null;
  messageBillingActive: boolean;
  includedMessages: number | null;
  availableMessages: number | null;
  includedRemaining: number | null;
  purchasedMessages: number | null;
  pendingDowngrade: PendingDowngrade | null;
  raw: string;
};

type BillingSnapshot = Omit<BillingEntitlementState, 'loading' | 'error' | 'raw'>;

function emptyBilling(): BillingSnapshot {
  return {
    planId: null,
    status: null,
    periodEnd: null,
    includedCredits: null,
    purchasedCredits: null,
    creditBalance: null,
    membershipRemaining: null,
    boughtRemaining: null,
    messageBillingActive: false,
    includedMessages: null,
    availableMessages: null,
    includedRemaining: null,
    purchasedMessages: null,
    pendingDowngrade: null,
  };
}

function seedBillingState(): BillingEntitlementState {
  const hit = cacheGet<BillingSnapshot>(queryKeys.billing());
  if (hit?.data) {
    return { ...emptyBilling(), ...hit.data, loading: false, error: null, raw: '' };
  }
  return { ...emptyBilling(), loading: true, error: null, raw: '' };
}

function persistBilling(state: BillingEntitlementState): void {
  const { loading: _loading, error: _error, raw: _raw, ...snap } = state;
  cacheSet(queryKeys.billing(), snap);
}

export function useBillingEntitlement() {
  const { tr } = useI18n();
  const [state, setState] = useState<BillingEntitlementState>(seedBillingState);

  const refresh = useCallback(async () => {
    setState((s) => ({
      ...s,
      loading: cacheGet(queryKeys.billing()) == null && s.planId == null && s.status == null,
    }));
    try {
      try {
        const catalog = await apiFetch('/api/public/plans', { schema: EntitlementsSchema });
        const plans = (catalog as { plans?: Array<Record<string, unknown>> }).plans;
        if (Array.isArray(plans)) applyPublicPlans(plans);
      } catch {
        /* keep seeded catalog; checkout still validates server-side */
      }
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
      let membershipRemaining: number | null = null;
      let boughtRemaining: number | null = null;
      let usage: Record<string, unknown> = {};
      try {
        const res = await apiFetch('/api/mobile/usage', { schema: UsageSchema });
        usage = res as Record<string, unknown>;
        creditBalance = asNumber(usage.credit_balance);
        membershipRemaining = asNumber(usage.membership_credits_remaining);
        boughtRemaining = asNumber(usage.purchased_credits_remaining);
      } catch {
        creditBalance = null;
      }
      if (
        (membershipRemaining == null || boughtRemaining == null) &&
        creditBalance != null
      ) {
        const split = splitCreditRemaining({
          included: typeof entitlement.included_credits === 'number' ? entitlement.included_credits : 0,
          purchased,
          available: creditBalance,
        });
        membershipRemaining = membershipRemaining ?? split.membership;
        boughtRemaining = boughtRemaining ?? split.bought;
      }
      const pendingDowngrade = parsePendingDowngrade(entitlement.pending_downgrade);
      const messageBillingActive =
        entitlement.message_billing_active === true || usage.message_billing_active === true;
      const next: BillingEntitlementState = {
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
        membershipRemaining,
        boughtRemaining,
        messageBillingActive,
        includedMessages:
          asNumber(entitlement.included_messages) ?? asNumber(usage.included_messages),
        availableMessages: messageBillingActive
          ? asNumber(entitlement.available_messages) ?? asNumber(usage.available_messages)
          : null,
        includedRemaining: messageBillingActive
          ? asNumber(entitlement.included_remaining) ?? asNumber(usage.included_remaining)
          : null,
        purchasedMessages: messageBillingActive
          ? asNumber(entitlement.purchased_messages) ?? asNumber(usage.purchased_messages)
          : null,
        pendingDowngrade,
        raw: __DEV__ ? JSON.stringify(data, null, 2) : '',
      };
      persistBilling(next);
      setState(next);
    } catch {
      setState((s) => {
        const painted =
          cacheGet(queryKeys.billing()) != null || s.planId != null || s.status != null;
        if (painted) {
          return { ...s, loading: false, error: tr('subLoadError') };
        }
        return { ...emptyBilling(), loading: false, error: tr('subLoadError'), raw: '' };
      });
    }
  }, [tr]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { ...state, refresh };
}

export { useBillingEntitlement as useBillingData };

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
