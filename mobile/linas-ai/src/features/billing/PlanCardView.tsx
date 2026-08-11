import { Ionicons } from '@expo/vector-icons';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import type { StringKey } from '../../i18n';
import { fonts, radii, spacing, useTheme } from '../../theme';
import type { PlanDefinition, PlanId } from './planCatalog';
import type { PlanCta } from './subscriptionCta';
import { accentForPlan } from './subscriptionCta';
import type { StorePrice } from './storePricing';

type Props = {
  plan: PlanDefinition;
  tr: (key: StringKey) => string;
  taglineKey: StringKey;
  featureKeys: StringKey[];
  price: StorePrice | null;
  cta: PlanCta;
  isCurrent: boolean;
  purchasing: boolean;
  onPressCta: () => void;
  onRetryPrice: () => void;
};

export function PlanCardView({
  plan,
  tr,
  taglineKey,
  featureKeys,
  price,
  cta,
  isCurrent,
  purchasing,
  onPressCta,
  onRetryPrice,
}: Props) {
  const { colors } = useTheme();
  const accent = accentForPlan(plan.id);
  const priceUnavailable = !price?.available;
  const showPreview = Boolean(price?.preview);
  const priceLabel = priceUnavailable
    ? tr('subPriceUnavailable')
    : `${price?.localizedPrice ?? ''}${tr('subPerMonth')}`;

  return (
    <View
      style={[
        styles.card,
        {
          backgroundColor: colors.surface,
          borderColor: isCurrent ? accent : colors.border,
          borderWidth: isCurrent ? 2 : 1,
        },
      ]}
      accessibilityRole="summary"
    >
      <View style={[styles.accentBar, { backgroundColor: accent }]} />
      <View style={styles.head}>
        <Text style={[styles.name, { color: colors.accentDeep }]}>{tr(planNameKey(plan.id))}</Text>
        <View style={styles.badges}>
          {plan.recommended ? (
            <View style={[styles.badge, { backgroundColor: colors.accentSoft }]}>
              <Text style={[styles.badgeText, { color: colors.accentDeep }]}>{tr('subRecommended')}</Text>
            </View>
          ) : null}
          {isCurrent ? (
            <View style={[styles.badge, { backgroundColor: colors.mintSoft }]}>
              <Text style={[styles.badgeText, { color: colors.mint }]}>{tr('subCtaCurrent')}</Text>
            </View>
          ) : null}
        </View>
      </View>
      <Text style={[styles.tagline, { color: colors.textMuted }]}>{tr(taglineKey)}</Text>
      <Text style={[styles.price, { color: colors.text }]} accessibilityLabel={priceLabel}>
        {priceLabel}
      </Text>
      {showPreview ? (
        <Text style={[styles.preview, { color: colors.warning }]}>{tr('subPricePreview')}</Text>
      ) : null}
      {priceUnavailable ? (
        <Pressable onPress={onRetryPrice} accessibilityRole="button" accessibilityLabel={tr('subRetryStore')}>
          <Text style={[styles.retry, { color: colors.accent }]}>{tr('subRetryStore')}</Text>
        </Pressable>
      ) : null}
      <View style={styles.feats}>
        {featureKeys.map((key) => (
          <View key={key} style={styles.featRow}>
            <Ionicons name="checkmark-circle" size={18} color={accent} accessibilityElementsHidden />
            <Text style={[styles.featText, { color: colors.text }]}>{tr(key)}</Text>
          </View>
        ))}
      </View>
      <Pressable
        onPress={onPressCta}
        disabled={!cta.enabled || purchasing || priceUnavailable}
        style={({ pressed }) => [
          styles.cta,
          {
            backgroundColor: cta.enabled && !priceUnavailable ? accent : colors.surfaceAlt,
            opacity: pressed && cta.enabled ? 0.85 : 1,
          },
        ]}
        accessibilityRole="button"
        accessibilityState={{ disabled: !cta.enabled || priceUnavailable }}
        accessibilityLabel={tr(cta.labelKey)}
      >
        <Text
          style={[
            styles.ctaText,
            { color: cta.enabled && !priceUnavailable ? colors.onAccent : colors.textMuted },
          ]}
        >
          {tr(cta.labelKey)}
        </Text>
      </Pressable>
    </View>
  );
}

function planNameKey(id: PlanId): StringKey {
  switch (id) {
    case 'lite':
      return 'subPlanLite';
    case 'starter':
      return 'subPlanStarter';
    case 'growth':
      return 'subPlanGrowth';
    case 'pro':
      return 'subPlanPro';
    case 'max':
      return 'subPlanMax';
  }
}

const styles = StyleSheet.create({
  card: {
    borderRadius: radii.lg,
    padding: spacing.lg,
    overflow: 'hidden',
    gap: 6,
  },
  accentBar: {
    position: 'absolute',
    left: 0,
    top: 0,
    bottom: 0,
    width: 4,
  },
  head: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 8,
    paddingLeft: 4,
  },
  name: { fontFamily: fonts.display, fontSize: 22 },
  badges: { flexDirection: 'row', gap: 6, flexWrap: 'wrap', justifyContent: 'flex-end' },
  badge: { borderRadius: radii.pill, paddingHorizontal: 10, paddingVertical: 4 },
  badgeText: { fontFamily: fonts.bodyMedium, fontSize: 11 },
  tagline: { fontFamily: fonts.body, fontSize: 13, lineHeight: 18, paddingLeft: 4 },
  price: { fontFamily: fonts.display, fontSize: 26, marginTop: 4, paddingLeft: 4 },
  preview: { fontFamily: fonts.bodyMedium, fontSize: 11, paddingLeft: 4 },
  retry: { fontFamily: fonts.bodyMedium, fontSize: 13, paddingLeft: 4, marginTop: 2 },
  feats: { marginTop: 8, gap: 8, paddingLeft: 4 },
  featRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 8 },
  featText: { flex: 1, fontFamily: fonts.body, fontSize: 13, lineHeight: 18 },
  cta: {
    marginTop: 12,
    borderRadius: radii.md,
    paddingVertical: 12,
    alignItems: 'center',
  },
  ctaText: { fontFamily: fonts.bodyMedium, fontSize: 15 },
});
