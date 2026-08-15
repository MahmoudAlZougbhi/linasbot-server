import { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, StyleSheet, Text } from 'react-native';

import { useI18n } from '../../i18n/LanguageContext';
import { fonts, spacing, useTheme } from '../../theme';
import { useModuleNav } from '../nav/ModuleNavContext';
import { ScreenChrome } from '../shared/ScreenChrome';
import { BuyCreditsSheet } from './BuyCreditsSheet';
import { ChoosePlanScreen } from './ChoosePlanScreen';
import { CurrentPlanScreen } from './CurrentPlanScreen';
import { DowngradeConfirmSheet } from './DowngradeConfirmSheet';
import type { BillingPeriod, CreditPackId } from './appleProductIds';
import { purchaseCredits, purchaseSubscription } from './iapPurchases';
import { cancelPendingDowngrade, scheduleDowngrade } from './planChangeApi';
import {
  PLAN_CATALOG,
  PLAN_ORDER,
  isPlanId,
  planRank,
  plansBelow,
  type PlanId,
} from './planCatalog';
import { isPaidActiveStatus, resolvePlanCta, statusLabelKey } from './subscriptionCta';
import { useBillingEntitlement, useBillingStorePrices } from './useBillingData';

type BrowseMode = 'upgrade' | 'downgrade';

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
  const [browseMode, setBrowseMode] = useState<BrowseMode>('upgrade');
  const [selected, setSelected] = useState<PlanId>('lite');
  const [creditsOpen, setCreditsOpen] = useState(false);
  const [downgradeConfirmOpen, setDowngradeConfirmOpen] = useState(false);

  const planId = entitlement.planId;
  const status = entitlement.status;
  const hasSub = Boolean(planId && isPaidActiveStatus(status));
  const view: 'current' | 'choose' = hasSub && !browsePlans ? 'current' : 'choose';

  useEffect(() => {
    setBrowsePlans(openChoosePlan);
    if (hasSub && planId) setSelected(planId);
  }, [hasSub, planId, nav.areaFocusNonce, openChoosePlan]);

  const visiblePlans = useMemo(() => {
    if (browseMode === 'downgrade' && planId && isPlanId(planId)) return plansBelow(planId);
    return PLAN_ORDER;
  }, [browseMode, planId]);

  useEffect(() => {
    if (browseMode === 'downgrade' && visiblePlans.length && !visiblePlans.includes(selected)) {
      setSelected(visiblePlans[visiblePlans.length - 1]);
    }
  }, [browseMode, selected, visiblePlans]);

  const runPurchase = useCallback(
    async (
      fn: () => Promise<{ ok: boolean; code?: string }>,
      successKey: 'subPurchaseSuccess' | 'subCreditsPurchaseSuccess' | 'subDowngradeScheduled' | 'subDowngradeCanceled',
      afterSuccess?: () => Promise<void>,
    ) => {
      if (purchasing) return;
      setPurchasing(true);
      store.setPurchaseNote(tr('subPurchasePending'));
      try {
        const result = await fn();
        if (result.ok) {
          if (afterSuccess) await afterSuccess();
          store.setPurchaseNote(tr(successKey));
          await entitlement.refresh();
          if (successKey === 'subPurchaseSuccess' || successKey === 'subDowngradeScheduled') {
            setBrowsePlans(false);
            setDowngradeConfirmOpen(false);
          }
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
  const onBack = browsePlans ? () => setBrowsePlans(false) : undefined;

  const periodEnd = entitlement.periodEnd;
  const renewsDate =
    periodEnd && Number.isFinite(periodEnd)
      ? new Date(periodEnd * 1000).toLocaleDateString(locale, {
          month: 'short',
          day: 'numeric',
          year: 'numeric',
        })
      : tr('subDateUnknown');
  const renewsLabel =
    status === 'canceled'
      ? `${tr('subAccessEnds')} ${renewsDate}`
      : `${tr('subRenewsPrefix')} ${renewsDate}`;
  const periodSuffix = period === 'yearly' ? tr('subPricePerYear') : tr('subPricePerMonth');

  const planCta =
    hasSub && planId && isPlanId(planId)
      ? resolvePlanCta(selected, planId, status, {
          storePriceAvailable: storeReady(selected),
          purchasePending: purchasing,
        })
      : resolvePlanCta(selected, null, status, {
          storePriceAvailable: storeReady(selected),
          purchasePending: purchasing,
        });

  const chooseTitle = browseMode === 'downgrade' ? tr('subDowngradeTitle') : tr('subChooseTitle');
  const chooseSubtitle =
    browseMode === 'downgrade' ? tr('subDowngradeSubtitle') : tr('subChooseSubtitle');

  return (
    <ScreenChrome
      title={view === 'current' ? tr('navSubscription') : chooseTitle}
      subtitle={view === 'current' ? tr('subCurrentSubtitle') : chooseSubtitle}
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
          pendingDowngrade={entitlement.pendingDowngrade}
          locale={locale}
          tr={tr}
          onBuyCredits={() => setCreditsOpen(true)}
          onUpgrade={() => {
            setBrowseMode('upgrade');
            setSelected(PLAN_ORDER.find((id) => planRank(id) > planRank(planId)) ?? planId);
            setBrowsePlans(true);
          }}
          onDowngrade={() => {
            const below = plansBelow(planId);
            setBrowseMode('downgrade');
            setSelected(below[below.length - 1] ?? planId);
            setBrowsePlans(true);
          }}
          onCancelPendingDowngrade={() => {
            if (!planId || !isPlanId(planId)) return;
            void runPurchase(
              () => purchaseSubscription(planId, period),
              'subDowngradeCanceled',
              async () => {
                await cancelPendingDowngrade();
              },
            );
          }}
          cancelingDowngrade={purchasing}
        />
      ) : (
        <ChoosePlanScreen
          selected={selected}
          currentPlan={hasSub && planId && isPlanId(planId) ? planId : null}
          visiblePlans={visiblePlans}
          mode={browseMode}
          period={period}
          priceLabel={priceFor(selected)}
          ctaEnabled={storeReady(selected) && !purchasing}
          purchasing={purchasing}
          ctaKind={planCta.kind}
          ctaLabelKey={planCta.labelKey}
          locale={locale}
          tr={tr}
          onSelect={setSelected}
          onPeriod={setPeriod}
          onChoose={() => {
            if (browseMode === 'downgrade') {
              setDowngradeConfirmOpen(true);
              return;
            }
            void runPurchase(() => purchaseSubscription(selected, period), 'subPurchaseSuccess');
          }}
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

      {planId && isPlanId(planId) ? (
        <DowngradeConfirmSheet
          visible={downgradeConfirmOpen}
          planId={selected}
          effectiveDateLabel={renewsDate}
          purchasing={purchasing}
          tr={tr}
          onConfirm={() =>
            void runPurchase(
              () => purchaseSubscription(selected, period),
              'subDowngradeScheduled',
              async () => {
                await scheduleDowngrade(selected);
              },
            )
          }
          onClose={() => setDowngradeConfirmOpen(false)}
        />
      ) : null}
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
