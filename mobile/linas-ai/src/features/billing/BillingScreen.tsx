import { useCallback, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
} from 'react-native';

import { useI18n } from '../../i18n/LanguageContext';
import type { StringKey } from '../../i18n';
import { fonts, spacing, useTheme } from '../../theme';
import { useModuleNav } from '../nav/ModuleNavContext';
import { ScreenChrome } from '../shared/ScreenChrome';
import { BillingPeriodToggle } from './BillingPeriodToggle';
import { BillingStoreActions } from './BillingStoreActions';
import { CommonFeaturesCard } from './CommonFeaturesCard';
import { CreditPacksSection } from './CreditPacksSection';
import { CurrentPlanSummary } from './CurrentPlanSummary';
import { PlanCardView } from './PlanCardView';
import type { BillingPeriod, CreditPackId } from './appleProductIds';
import { appleProductIdForPlan } from './appleProductIds';
import {
  openManageSubscriptions,
  purchaseCredits,
  purchaseSubscription,
  requestRefundForProduct,
  restorePurchases,
} from './iapPurchases';
import { PLAN_CATALOG, PLAN_ORDER, type PlanId } from './planCatalog';
import { resolvePlanCta } from './subscriptionCta';
import { useBillingEntitlement, useBillingStorePrices } from './useBillingData';

type Props = Record<string, never>;

const FEATURE_KEYS: Record<PlanId, StringKey[]> = {
  lite: [
    'subLiteFeatCredits',
    'subLiteFeatDm',
    'subLiteFeatFaq',
    'subLiteFeatOwner',
    'subLiteFeatComments',
  ],
  starter: [
    'subStarterFeatCredits',
    'subStarterFeatDm',
    'subStarterFeatComments',
    'subStarterFeatFaq',
    'subStarterFeatSeats',
  ],
  growth: [
    'subGrowthFeatCredits',
    'subGrowthFeatDm',
    'subGrowthFeatComments',
    'subGrowthFeatFaq',
    'subGrowthFeatSeats',
  ],
  pro: [
    'subProFeatCredits',
    'subProFeatDm',
    'subProFeatComments',
    'subProFeatFaq',
    'subProFeatSeats',
  ],
  max: [
    'subMaxFeatCredits',
    'subMaxFeatDm',
    'subMaxFeatComments',
    'subMaxFeatFaq',
    'subMaxFeatSeats',
  ],
};

const TAGLINE_KEYS: Record<PlanId, StringKey> = {
  lite: 'subLiteTagline',
  starter: 'subStarterTagline',
  growth: 'subGrowthTagline',
  pro: 'subProTagline',
  max: 'subMaxTagline',
};

export function BillingScreen(_props: Props = {}) {
  const { colors } = useTheme();
  const { tr, language } = useI18n();
  const nav = useModuleNav();
  const [period, setPeriod] = useState<BillingPeriod>('monthly');
  const [purchasing, setPurchasing] = useState(false);
  const tapLock = useRef(false);
  const locale = language === 'ar' ? 'ar' : language === 'fr' ? 'fr' : 'en';

  const entitlement = useBillingEntitlement();
  const store = useBillingStorePrices(period, locale);
  const { planId, status } = entitlement;

  const mapResultNote = useCallback(
    (code: string) => {
      if (code === 'cancel') return tr('subPurchaseCanceled');
      if (code === 'unavailable') return tr('subStoreUnavailable');
      if (code === 'verify_failed') return tr('subPurchaseVerifyFailed');
      return tr('subPurchaseError');
    },
    [tr],
  );

  const runPurchase = useCallback(
    async (fn: () => Promise<{ ok: boolean; code?: string }>, successKey: StringKey) => {
      if (tapLock.current || purchasing) return;
      tapLock.current = true;
      setPurchasing(true);
      store.setPurchaseNote(tr('subPurchasePending'));
      try {
        const result = await fn();
        if (result.ok) {
          store.setPurchaseNote(tr(successKey));
          await entitlement.refresh();
        } else {
          store.setPurchaseNote(mapResultNote(result.code || 'error'));
        }
      } finally {
        tapLock.current = false;
        setPurchasing(false);
      }
    },
    [entitlement, mapResultNote, purchasing, store, tr],
  );

  const onRestore = useCallback(async () => {
    if (purchasing) return;
    setPurchasing(true);
    store.setPurchaseNote(tr('subRestorePending'));
    try {
      const result = await restorePurchases();
      if (result.ok) {
        store.setPurchaseNote(tr('subRestoreSuccess'));
        await entitlement.refresh();
      } else if (result.code === 'unavailable') {
        store.setPurchaseNote(tr('subRestoreUnavailable'));
      } else {
        store.setPurchaseNote(tr('subRestoreError'));
      }
    } finally {
      setPurchasing(false);
    }
  }, [entitlement, purchasing, store, tr]);

  const onRefund = useCallback(async () => {
    if (!planId || purchasing) return;
    setPurchasing(true);
    try {
      const result = await requestRefundForProduct(appleProductIdForPlan(planId, period));
      if (result.ok) store.setPurchaseNote(tr('subRefundSubmitted'));
      else if (result.code === 'cancel') store.setPurchaseNote(tr('subPurchaseCanceled'));
      else store.setPurchaseNote(tr('subRefundUnavailable'));
    } finally {
      setPurchasing(false);
    }
  }, [period, planId, purchasing, store, tr]);

  const cards = useMemo(() => PLAN_ORDER.map((id) => PLAN_CATALOG[id]), []);
  const showRefund =
    Platform.OS === 'ios' &&
    Boolean(planId) &&
    Boolean(status && ['active', 'grace', 'canceled'].includes(String(status).toLowerCase()));

  return (
    <ScreenChrome title={tr('navSubscription')} subtitle={tr('subSubtitle')}>
      <Pressable
        onPress={() => nav.startNewChat()}
        accessibilityRole="button"
        accessibilityLabel={tr('subBackToChat')}
        style={styles.back}
      >
        <Text style={[styles.backText, { color: colors.accent }]}>{tr('subBackToChat')}</Text>
      </Pressable>

      {entitlement.loading || store.storeLoading ? (
        <ActivityIndicator color={colors.accent} />
      ) : null}
      {entitlement.error ? (
        <Text style={[styles.error, { color: colors.danger }]}>{entitlement.error}</Text>
      ) : null}
      {store.purchaseNote ? (
        <Text style={[styles.note, { color: colors.warning }]}>{store.purchaseNote}</Text>
      ) : null}

      <ScrollView contentContainerStyle={styles.list} showsVerticalScrollIndicator={false}>
        <CurrentPlanSummary
          tr={tr}
          planId={planId}
          status={status}
          periodEnd={entitlement.periodEnd}
          includedCredits={entitlement.includedCredits}
          purchasedCredits={entitlement.purchasedCredits}
          creditBalance={entitlement.creditBalance}
          locale={locale}
          onManage={() => void openManageSubscriptions()}
        />

        <Text style={[styles.creditsExplain, { color: colors.textMuted }]}>
          {tr('subCreditsExplain')}
        </Text>
        <Text style={[styles.creditsExplain, { color: colors.textMuted }]}>
          {tr('subOwnerSeatNote')}
        </Text>

        <BillingPeriodToggle period={period} onChange={setPeriod} tr={tr} />
        <CommonFeaturesCard tr={tr} />

        {cards.map((plan) => {
          const price = store.storePrices[plan.id];
          const cta = resolvePlanCta(plan.id, planId, status, {
            storePriceAvailable: Boolean(price?.available),
            purchasePending: purchasing,
          });
          return (
            <PlanCardView
              key={`${plan.id}-${period}`}
              plan={plan}
              tr={tr}
              taglineKey={TAGLINE_KEYS[plan.id]}
              featureKeys={FEATURE_KEYS[plan.id]}
              price={price}
              period={period}
              cta={cta}
              isCurrent={planId === plan.id && Boolean(status && status !== 'none')}
              purchasing={purchasing}
              onPressCta={() =>
                void runPurchase(
                  () => purchaseSubscription(plan.id, period),
                  'subPurchaseSuccess',
                )
              }
              onRetryPrice={() => void store.refreshStore()}
            />
          );
        })}

        {Platform.OS === 'ios' ? (
          <CreditPacksSection
            tr={tr}
            prices={store.creditPrices}
            purchasing={purchasing}
            onBuy={(credits: CreditPackId) =>
              void runPurchase(() => purchaseCredits(credits), 'subCreditsPurchaseSuccess')
            }
            locale={locale}
          />
        ) : null}

        <BillingStoreActions
          tr={tr}
          showRefund={showRefund}
          busy={purchasing}
          onRestore={() => void onRestore()}
          onManage={() => void openManageSubscriptions()}
          onRefund={() => void onRefund()}
        />

        {__DEV__ && entitlement.raw ? (
          <Text style={[styles.mono, { color: colors.textMuted }]}>{entitlement.raw}</Text>
        ) : null}
      </ScrollView>
    </ScreenChrome>
  );
}

const styles = StyleSheet.create({
  back: { marginBottom: spacing.sm },
  backText: { fontFamily: fonts.bodyMedium, fontSize: 14 },
  list: { paddingBottom: 48, gap: spacing.md },
  creditsExplain: { fontFamily: fonts.body, fontSize: 13, lineHeight: 18 },
  error: { fontFamily: fonts.body, marginBottom: spacing.sm },
  note: { fontFamily: fonts.body, fontSize: 13, marginBottom: spacing.sm },
  mono: { fontFamily: 'Courier', fontSize: 11, lineHeight: 15 },
});
