import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { StringKey } from '../../i18n';
import { fonts, radii, spacing, useTheme } from '../../theme';
import { CurrentPlanHeroCard } from './CurrentPlanHeroCard';
import { PlanIncludedList } from './PlanIncludedList';
import { PlanNotIncluded } from './PlanNotIncluded';
import { SmartAnswersInfo } from './SmartAnswersInfo';
import { PLAN_CATALOG, type PlanId } from './planCatalog';
import { entitlementsForPlan, PLAN_NAME_KEY } from './planEntitlements';

type Props = {
  planId: PlanId;
  statusLabel: string;
  priceLabel: string;
  renewsLabel: string;
  creditBalance: number | null;
  locale: string;
  tr: (key: StringKey) => string;
  onBuyCredits: () => void;
  onUpgrade: () => void;
};

export function CurrentPlanScreen({
  planId,
  statusLabel,
  priceLabel,
  renewsLabel,
  creditBalance,
  locale,
  tr,
  onBuyCredits,
  onUpgrade,
}: Props) {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const plan = PLAN_CATALOG[planId];
  const ents = entitlementsForPlan(plan);
  const available =
    creditBalance != null && Number.isFinite(creditBalance)
      ? creditBalance.toLocaleString(locale)
      : tr('subCreditsMissing');
  const includedEachMonth = tr('subIncludedEachMonth').replace(
    '{n}',
    plan.includedCredits.toLocaleString(locale),
  );
  const includesTitle = tr('subWhatIncludes').replace('{plan}', tr(PLAN_NAME_KEY[planId]));

  return (
    <View style={styles.root}>
      <ScrollView contentContainerStyle={styles.list} showsVerticalScrollIndicator={false}>
        <CurrentPlanHeroCard
          planId={planId}
          statusLabel={statusLabel}
          priceLabel={priceLabel}
          renewsLabel={renewsLabel}
          availableLabel={available}
          includedEachMonth={includedEachMonth}
          tr={tr}
          onBuyCredits={onBuyCredits}
        />
        <PlanIncludedList
          title={includesTitle}
          rows={ents.included}
          tr={tr}
          locale={locale}
          variant="current"
        />
        <SmartAnswersInfo tr={tr} variant="current" />
        <PlanNotIncluded ids={ents.excluded} tr={tr} variant="current" />
      </ScrollView>
      <View style={[styles.footer, { paddingBottom: Math.max(insets.bottom, 12) }]}>
        <Pressable
          onPress={onUpgrade}
          accessibilityRole="button"
          accessibilityLabel={tr('subUpgradePlan')}
          style={({ pressed }) => [
            styles.cta,
            { backgroundColor: colors.accent, opacity: pressed ? 0.88 : 1 },
          ]}
        >
          <Text style={[styles.ctaText, { color: colors.onAccent }]}>{tr('subUpgradePlan')}</Text>
        </Pressable>
        <Text style={[styles.footNote, { color: colors.textMuted }]}>{tr('subCreditsRefreshNote')}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  list: { gap: spacing.md, paddingBottom: spacing.md },
  footer: { gap: 10, paddingTop: spacing.sm },
  cta: {
    borderRadius: radii.md,
    paddingVertical: 16,
    alignItems: 'center',
  },
  ctaText: { fontFamily: fonts.bodyMedium, fontSize: 16, fontWeight: '700' },
  footNote: {
    fontFamily: fonts.body,
    fontSize: 12,
    textAlign: 'center',
    lineHeight: 16,
  },
});
