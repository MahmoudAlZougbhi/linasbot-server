import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { StringKey } from '../../i18n';
import { fonts, radii, spacing, useTheme } from '../../theme';
import { BillingPeriodToggle } from './BillingPeriodToggle';
import { PlanChipRow } from './PlanChipRow';
import { PlanDetailCard } from './PlanDetailCard';
import type { BillingPeriod } from './appleProductIds';
import type { PlanId } from './planCatalog';
import { PLAN_CHOOSE_CTA } from './planEntitlements';

type Props = {
  selected: PlanId;
  currentPlan: PlanId | null;
  period: BillingPeriod;
  priceLabel: string;
  ctaEnabled: boolean;
  purchasing: boolean;
  locale: string;
  tr: (key: StringKey) => string;
  onSelect: (id: PlanId) => void;
  onPeriod: (period: BillingPeriod) => void;
  onChoose: () => void;
};

export function ChoosePlanScreen({
  selected,
  currentPlan,
  period,
  priceLabel,
  ctaEnabled,
  purchasing,
  locale,
  tr,
  onSelect,
  onPeriod,
  onChoose,
}: Props) {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const isCurrent = currentPlan === selected;
  const ctaLabel = isCurrent ? tr('subYourPlan') : tr(PLAN_CHOOSE_CTA[selected]);
  const periodSuffix = period === 'yearly' ? tr('subPricePerYear') : tr('subPricePerMonth');

  return (
    <View style={styles.root}>
      <ScrollView contentContainerStyle={styles.list} showsVerticalScrollIndicator={false}>
        <BillingPeriodToggle period={period} onChange={onPeriod} tr={tr} />
        <PlanChipRow
          selected={selected}
          currentPlan={currentPlan}
          tr={tr}
          onSelect={onSelect}
        />
        <PlanDetailCard
          planId={selected}
          priceLabel={priceLabel}
          periodSuffix={periodSuffix}
          locale={locale}
          tr={tr}
        />
      </ScrollView>
      <View style={[styles.footer, { paddingBottom: Math.max(insets.bottom, 12) }]}>
        <Pressable
          onPress={onChoose}
          disabled={!ctaEnabled || purchasing || isCurrent}
          accessibilityRole="button"
          accessibilityState={{ disabled: !ctaEnabled || isCurrent }}
          accessibilityLabel={ctaLabel}
          style={({ pressed }) => [
            styles.cta,
            {
              backgroundColor: ctaEnabled && !isCurrent ? colors.accent : colors.surfaceAlt,
              opacity: pressed && ctaEnabled && !isCurrent ? 0.88 : 1,
            },
          ]}
        >
          <Text
            style={[
              styles.ctaText,
              { color: ctaEnabled && !isCurrent ? colors.onAccent : colors.textMuted },
            ]}
          >
            {ctaLabel}
          </Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  list: { gap: spacing.md, paddingBottom: spacing.md },
  footer: { paddingTop: spacing.sm },
  cta: {
    borderRadius: radii.md,
    paddingVertical: 16,
    alignItems: 'center',
  },
  ctaText: { fontFamily: fonts.bodyMedium, fontSize: 16, fontWeight: '700' },
});
