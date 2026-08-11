import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Linking,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { z } from 'zod';

import { apiFetch } from '../../api/client';
import { LEGAL_URLS } from '../../config';
import { useI18n } from '../../i18n/LanguageContext';
import type { StringKey } from '../../i18n';
import { fonts, spacing, useTheme } from '../../theme';
import { useModuleNav } from '../nav/ModuleNavContext';
import { ScreenChrome } from '../shared/ScreenChrome';
import { CommonFeaturesCard } from './CommonFeaturesCard';
import { CurrentPlanSummary } from './CurrentPlanSummary';
import { PlanCardView } from './PlanCardView';
import { isPlanId, PLAN_CATALOG, PLAN_ORDER, type PlanId } from './planCatalog';
import { resolvePlanCta } from './subscriptionCta';
import { loadStorePrices, previewCatalogPrices, type StorePrice } from './storePricing';

const EntitlementsSchema = z.object({ success: z.boolean() }).passthrough();
const UsageSchema = z.object({ success: z.literal(true) }).passthrough();

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
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [planId, setPlanId] = useState<PlanId | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [periodEnd, setPeriodEnd] = useState<number | null>(null);
  const [includedCredits, setIncludedCredits] = useState<number | null>(null);
  const [purchasedCredits, setPurchasedCredits] = useState<number | null>(null);
  const [creditBalance, setCreditBalance] = useState<number | null>(null);
  const [storePrices, setStorePrices] = useState<Record<PlanId, StorePrice | null>>({
    lite: null,
    starter: null,
    growth: null,
    pro: null,
    max: null,
  });
  const [storeLoading, setStoreLoading] = useState(false);
  const [purchasing, setPurchasing] = useState(false);
  const [purchaseNote, setPurchaseNote] = useState<string | null>(null);
  const tapLock = useRef(false);
  const [raw, setRaw] = useState('');

  const locale = language === 'ar' ? 'ar' : language === 'fr' ? 'fr' : 'en';

  const refreshEntitlement = useCallback(async () => {
    setLoading(true);
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
      setPlanId(isPlanId(p) ? p : null);
      setStatus(typeof entitlement.status === 'string' ? entitlement.status : null);
      setPeriodEnd(
        typeof entitlement.current_period_end === 'number' ? entitlement.current_period_end : null,
      );
      setIncludedCredits(
        typeof entitlement.included_credits === 'number' ? entitlement.included_credits : null,
      );
      const purchased =
        typeof entitlement.purchased_credits === 'number'
          ? entitlement.purchased_credits
          : typeof entitlement.extra_credits === 'number'
            ? entitlement.extra_credits
            : null;
      setPurchasedCredits(purchased);
      if (__DEV__) setRaw(JSON.stringify(data, null, 2));
      else setRaw('');
      setError(null);
    } catch {
      setError(tr('subLoadError'));
      setPlanId(null);
      setStatus(null);
      setRaw('');
    } finally {
      setLoading(false);
    }
  }, [tr]);

  const refreshUsage = useCallback(async () => {
    try {
      const res = await apiFetch('/api/mobile/usage', { schema: UsageSchema });
      const bal = (res as Record<string, unknown>).credit_balance;
      setCreditBalance(typeof bal === 'number' ? bal : null);
    } catch {
      setCreditBalance(null);
    }
  }, []);

  const refreshStore = useCallback(async () => {
    setStoreLoading(true);
    setPurchaseNote(null);
    try {
      const state = await loadStorePrices(Platform.OS);
      setStorePrices(state.prices);
      if (state.error && __DEV__) {
        setStorePrices(previewCatalogPrices(locale));
        setPurchaseNote(tr('subPricePreview'));
      }
    } finally {
      setStoreLoading(false);
    }
  }, [locale, tr]);

  useEffect(() => {
    void refreshEntitlement();
    void refreshUsage();
    void refreshStore();
  }, [refreshEntitlement, refreshUsage, refreshStore]);

  const onPurchase = useCallback(
    (target: PlanId) => {
      if (tapLock.current || purchasing) return;
      tapLock.current = true;
      setPurchasing(true);
      setPurchaseNote(tr('subPurchaseBlocked'));
      setTimeout(() => {
        tapLock.current = false;
        setPurchasing(false);
      }, 800);
      void target;
    },
    [purchasing, tr],
  );

  const cards = useMemo(() => PLAN_ORDER.map((id) => PLAN_CATALOG[id]), []);

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

      {loading || storeLoading ? <ActivityIndicator color={colors.accent} /> : null}
      {error ? <Text style={[styles.error, { color: colors.danger }]}>{error}</Text> : null}
      {purchaseNote ? (
        <Text style={[styles.note, { color: colors.warning }]}>{purchaseNote}</Text>
      ) : null}

      <ScrollView contentContainerStyle={styles.list} showsVerticalScrollIndicator={false}>
        <CurrentPlanSummary
          tr={tr}
          planId={planId}
          status={status}
          periodEnd={periodEnd}
          includedCredits={includedCredits}
          purchasedCredits={purchasedCredits}
          creditBalance={creditBalance}
          locale={locale}
          onManage={() => void Linking.openURL(LEGAL_URLS.terms)}
        />

        <Text style={[styles.creditsExplain, { color: colors.textMuted }]}>
          {tr('subCreditsExplain')}
        </Text>
        <Text style={[styles.creditsExplain, { color: colors.textMuted }]}>
          {tr('subOwnerSeatNote')}
        </Text>

        <CommonFeaturesCard tr={tr} />

        {cards.map((plan) => {
          const price = storePrices[plan.id];
          const cta = resolvePlanCta(plan.id, planId, status, {
            storePriceAvailable: Boolean(price?.available),
            purchasePending: purchasing,
          });
          return (
            <PlanCardView
              key={plan.id}
              plan={plan}
              tr={tr}
              taglineKey={TAGLINE_KEYS[plan.id]}
              featureKeys={FEATURE_KEYS[plan.id]}
              price={price}
              cta={cta}
              isCurrent={planId === plan.id && Boolean(status && status !== 'none')}
              purchasing={purchasing}
              onPressCta={() => onPurchase(plan.id)}
              onRetryPrice={() => void refreshStore()}
            />
          );
        })}

        <View style={[styles.footer, { borderColor: colors.border }]}>
          <Text style={[styles.footerText, { color: colors.textMuted }]}>{tr('subFooterStore')}</Text>
          <Text style={[styles.footerText, { color: colors.textMuted }]}>{tr('subFooterReset')}</Text>
          <Text style={[styles.footerText, { color: colors.textMuted }]}>{tr('subFooterPurchased')}</Text>
          <Pressable
            onPress={() => setPurchaseNote(tr('subRestoreUnavailable'))}
            accessibilityRole="button"
          >
            <Text style={[styles.link, { color: colors.accent }]}>{tr('subRestore')}</Text>
          </Pressable>
          <View style={styles.legalRow}>
            <Pressable onPress={() => void Linking.openURL(LEGAL_URLS.terms)}>
              <Text style={[styles.link, { color: colors.accent }]}>{tr('terms')}</Text>
            </Pressable>
            <Text style={{ color: colors.textDim }}> · </Text>
            <Pressable onPress={() => void Linking.openURL(LEGAL_URLS.privacy)}>
              <Text style={[styles.link, { color: colors.accent }]}>{tr('privacy')}</Text>
            </Pressable>
          </View>
        </View>

        {__DEV__ && raw ? (
          <Text style={[styles.mono, { color: colors.textMuted }]}>{raw}</Text>
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
  footer: {
    borderTopWidth: 1,
    paddingTop: spacing.md,
    gap: 6,
    marginTop: spacing.sm,
  },
  footerText: { fontFamily: fonts.body, fontSize: 12, lineHeight: 17 },
  legalRow: { flexDirection: 'row', alignItems: 'center', marginTop: 4 },
  link: { fontFamily: fonts.bodyMedium, fontSize: 13 },
  error: { fontFamily: fonts.body, marginBottom: spacing.sm },
  note: { fontFamily: fonts.body, fontSize: 13, marginBottom: spacing.sm },
  mono: { fontFamily: 'Courier', fontSize: 11, lineHeight: 15 },
});
