import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, StyleSheet, Text } from 'react-native';

import { useI18n } from '../../i18n/LanguageContext';
import { fonts, spacing, useTheme } from '../../theme';
import { useModuleNav } from '../nav/ModuleNavContext';
import { ScreenChrome } from '../shared/ScreenChrome';
import { BuyCreditsSheet } from './BuyCreditsSheet';
import { ChoosePlanScreen } from './ChoosePlanScreen';
import { CurrentPlanScreen } from './CurrentPlanScreen';
import type { BillingPeriod, CreditPackId } from './appleProductIds';
import {
  purchaseCredits,
  purchaseSubscription,
} from './iapPurchases';
import { PLAN_CATALOG, isPlanId, type PlanId } from './planCatalog';
import { isPaidActiveStatus, statusLabelKey } from './subscriptionCta';
import { useBillingEntitlement, useBillingStorePrices } from './useBillingData';

type Props = { openChoosePlan?: boolean };

export function BillingScreen({ openChoosePlan = false }: Props) {
  const { colors } = useTheme();
  const { tr, language } = useI18n();
  const nav = useModuleNav();
  const locale = language === 'ar' ? 'ar' : language === 'fr' ? 'fr' : 'en';
  const entitlement = useBillingEntitlement();
  const [period, setPeriod] = useState<BillingPeriod>('monthly');
  const store = useBillingStorePrices(period, locale);
  const [purchasing, setPurchasing] = useState(false);
  const [browsePlans, setBrowsePlans] = useState(false);
  const [selected, setSelected] = useState<PlanId>('lite');
  const [creditsOpen, setCreditsOpen] = useState(false);

  const planId = entitlement.planId;
  const status = entitlement.status;
  const hasSub = Boolean(planId && isPaidActiveStatus(status));
  const view: 'current' | 'choose' = hasSub && !browsePlans ? 'current' : 'choose';

  useEffect(() => {
    setBrowsePlans(openChoosePlan);
    if (hasSub && planId) setSelected(planId);
  }, [hasSub, planId, nav.areaFocusNonce, openChoosePlan]);

  const runPurchase = useCallback(
    async (fn: () => Promise<{ ok: boolean; code?: string }>, successKey: 'subPurchaseSuccess' | 'subCreditsPurchaseSuccess') => {
      if (purchasing) return;
      setPurchasing(true);
      store.setPurchaseNote(tr('subPurchasePending'));
      try {
        const result = await fn();
        if (result.ok) {
          store.setPurchaseNote(tr(successKey));
          await entitlement.refresh();
          if (successKey === 'subPurchaseSuccess') setBrowsePlans(false);
          if (successKey === 'subCreditsPurchaseSuccess') setCreditsOpen(false);
        } else if (result.code === 'cancel') {
          store.setPurchaseNote(tr('subPurchaseCanceled'));
        } else if (result.code === 'unavailable') {
          store.setPurchaseNote(tr('subStoreUnavailable'));
        } else if (result.code === 'verify_failed') {
          store.setPurchaseNote(tr('subPurchaseVerifyFailed'));
        } else {
          store.setPurchaseNote(tr('subPurchaseError'));
        }
      } finally {
        setPurchasing(false);
      }
    },
    [entitlement, purchasing, store, tr],
  );

  const priceFor = (id: PlanId) => {
    const hit = store.storePrices[id];
    if (hit?.available && hit.localizedPrice) return hit.localizedPrice;
    return formatUsd(PLAN_CATALOG[id].catalogPriceUsd);
  };
  const storeReady = (id: PlanId) => Boolean(store.storePrices[id]?.available);

  /** Drawer → Subscription is always hamburger. Back only after Upgrade → Choose a plan. */
  const onBack = browsePlans ? () => setBrowsePlans(false) : undefined;

  const periodEnd = entitlement.periodEnd;
  const renewsDate =
    periodEnd && Number.isFinite(periodEnd)
      ? new Date(periodEnd * 1000).toLocaleDateString(locale, { month: 'short', day: 'numeric' })
      : tr('subDateUnknown');
  const renewsLabel =
    status === 'canceled'
      ? `${tr('subAccessEnds')} ${renewsDate}`
      : `${tr('subRenewsPrefix')} ${renewsDate}`;
  const periodSuffix = period === 'yearly' ? tr('subPricePerYear') : tr('subPricePerMonth');

  return (
    <ScreenChrome
      title={view === 'current' ? tr('navSubscription') : tr('subChooseTitle')}
      subtitle={view === 'current' ? tr('subCurrentSubtitle') : tr('subChooseSubtitle')}
      onBack={onBack}
    >
      {entitlement.error ? (
        <Text style={[styles.error, { color: colors.danger }]}>{entitlement.error}</Text>
      ) : null}
      {store.purchaseNote ? (
        <Text style={[styles.note, { color: colors.warning }]}>{store.purchaseNote}</Text>
      ) : null}
      {entitlement.loading ? (
        <ActivityIndicator color={colors.accent} style={styles.spinner} />
      ) : view === 'current' && planId && isPlanId(planId) ? (
        <CurrentPlanScreen
          planId={planId}
          statusLabel={tr(statusLabelKey(status))}
          priceLabel={`${priceFor(planId)} ${periodSuffix}`}
          renewsLabel={renewsLabel}
          creditBalance={entitlement.creditBalance}
          locale={locale}
          tr={tr}
          onBuyCredits={() => setCreditsOpen(true)}
          onUpgrade={() => {
            setSelected(planId);
            setBrowsePlans(true);
          }}
        />
      ) : (
        <ChoosePlanScreen
          selected={selected}
          currentPlan={hasSub && planId && isPlanId(planId) ? planId : null}
          period={period}
          priceLabel={priceFor(selected)}
          ctaEnabled={storeReady(selected) && !purchasing}
          purchasing={purchasing}
          locale={locale}
          tr={tr}
          onSelect={setSelected}
          onPeriod={setPeriod}
          onChoose={() =>
            void runPurchase(
              () => purchaseSubscription(selected, period),
              'subPurchaseSuccess',
            )
          }
        />
      )}

      <BuyCreditsSheet
        visible={creditsOpen}
        prices={store.creditPrices}
        purchasing={purchasing}
        locale={locale}
        tr={tr}
        onClose={() => setCreditsOpen(false)}
        onBuy={(credits: CreditPackId) =>
          void runPurchase(() => purchaseCredits(credits), 'subCreditsPurchaseSuccess')
        }
      />
    </ScreenChrome>
  );
}

function formatUsd(amount: number): string {
  return `$${amount.toFixed(2)}`;
}

const styles = StyleSheet.create({
  spinner: { marginBottom: spacing.sm },
  error: { fontFamily: fonts.body, marginBottom: spacing.sm },
  note: { fontFamily: fonts.body, fontSize: 13, marginBottom: spacing.sm },
});
