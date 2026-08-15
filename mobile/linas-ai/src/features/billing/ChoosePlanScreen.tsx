import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { StringKey } from '../../i18n';
import { fonts, radii, spacing, useTheme } from '../../theme';
import { BillingPeriodToggle } from './BillingPeriodToggle';
import { PlanChipRow } from './PlanChipRow';
import { PlanDetailCard } from './PlanDetailCard';
import type { BillingPeriod } from './appleProductIds';
import type { PlanId } from './planCatalog';
import { accentForPlan, planOnAccent } from './planColors';
import type { CtaKind } from './subscriptionCta';

type Props = {
  selected: PlanId;
  currentPlan: PlanId | null;
  visiblePlans: PlanId[];
  mode: 'choose' | 'upgrade' | 'downgrade';
  period: BillingPeriod;
  priceLabel: string;
  ctaEnabled: boolean;
  purchasing: boolean;
  ctaKind: CtaKind;
  ctaLabelKey: StringKey;
  locale: string;
  tr: (key: StringKey) => string;
  onSelect: (id: PlanId) => void;
  onPeriod: (period: BillingPeriod) => void;
  onChoose: () => void;
};

export function ChoosePlanScreen({
  selected,
  currentPlan,
  visiblePlans,
  mode,
  period,
  priceLabel,
  ctaEnabled,
  purchasing,
  ctaKind,
  ctaLabelKey,
  locale,
  tr,
  onSelect,
  onPeriod,
  onChoose,
}: Props) {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const isCurrent = currentPlan === selected;
  const ctaLabel = isCurrent ? tr('subYourPlan') : tr(ctaLabelKey);
  const periodSuffix = period === 'yearly' ? tr('subPricePerYear') : tr('subPricePerMonth');
  const ctaAccent = accentForPlan(selected);
  const ctaDisabled = !ctaEnabled || purchasing || isCurrent || ctaKind === 'disabled' || ctaKind === 'current';

  return (
    <View style={styles.root}>
      <ScrollView contentContainerStyle={styles.list} showsVerticalScrollIndicator={false}>
        {mode !== 'downgrade' ? (
          <BillingPeriodToggle period={period} onChange={onPeriod} tr={tr} />
        ) : null}
        <PlanChipRow
          selected={selected}
          currentPlan={currentPlan}
          visiblePlans={visiblePlans}
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
          disabled={ctaDisabled}
          accessibilityRole="button"
          accessibilityState={{ disabled: ctaDisabled }}
          accessibilityLabel={ctaLabel}
          style={({ pressed }) => [
            styles.cta,
            {
              backgroundColor: ctaEnabled && !ctaDisabled ? ctaAccent : colors.surfaceAlt,
              opacity: pressed && ctaEnabled && !ctaDisabled ? 0.88 : 1,
            },
          ]}
        >
          <Text
            style={[
              styles.ctaText,
              {
                color: ctaEnabled && !ctaDisabled ? planOnAccent(selected) : colors.textMuted,
              },
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
