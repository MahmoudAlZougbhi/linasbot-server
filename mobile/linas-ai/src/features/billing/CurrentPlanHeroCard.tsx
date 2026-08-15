import { Pressable, StyleSheet, Text, View } from 'react-native';

import type { StringKey } from '../../i18n';
import { fonts, radii, spacing, useTheme } from '../../theme';
import { PLAN_NAME_KEY } from './planEntitlements';
import type { PlanId } from './planCatalog';

type Props = {
  planId: PlanId;
  statusLabel: string;
  priceLabel: string;
  renewsLabel: string;
  availableLabel: string;
  includedEachMonth: string;
  tr: (key: StringKey) => string;
  onBuyCredits: () => void;
};

export function CurrentPlanHeroCard({
  planId,
  statusLabel,
  priceLabel,
  renewsLabel,
  availableLabel,
  includedEachMonth,
  tr,
  onBuyCredits,
}: Props) {
  const { colors } = useTheme();
  return (
    <View style={[styles.card, { backgroundColor: colors.surfaceAlt }]}>
      <Text style={[styles.kicker, { color: colors.accent }]}>{tr('subCurrentPlanKicker')}</Text>
      <View style={styles.nameRow}>
        <Text style={[styles.name, { color: colors.text }]}>{tr(PLAN_NAME_KEY[planId])}</Text>
        <View style={styles.status}>
          <View style={[styles.dot, { backgroundColor: colors.success }]} />
          <Text style={[styles.statusText, { color: colors.success }]}>{statusLabel}</Text>
        </View>
      </View>
      <View style={styles.metaRow}>
        <Text style={[styles.price, { color: colors.accent }]}>{priceLabel}</Text>
        <Text style={[styles.renews, { color: colors.textMuted }]}>{renewsLabel}</Text>
      </View>

      <View style={[styles.credits, { backgroundColor: colors.surface, borderColor: colors.border }]}>
        <View style={styles.creditsMeta}>
          <Text style={[styles.creditsKicker, { color: colors.textMuted }]}>
            {tr('subAvailableCredits')}
          </Text>
          <Text style={[styles.creditsValue, { color: colors.text }]}>{availableLabel}</Text>
          <Text style={[styles.creditsHint, { color: colors.textMuted }]}>{includedEachMonth}</Text>
        </View>
        <Pressable
          onPress={onBuyCredits}
          accessibilityRole="button"
          accessibilityLabel={tr('subBuyCredits')}
          style={({ pressed }) => [
            styles.buy,
            { borderColor: colors.accent, opacity: pressed ? 0.7 : 1 },
          ]}
        >
          <Text style={[styles.buyText, { color: colors.accent }]}>{tr('subBuyCredits')}</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: radii.lg,
    padding: spacing.lg,
    gap: 6,
  },
  kicker: {
    fontFamily: fonts.bodyMedium,
    fontSize: 11,
    letterSpacing: 0.8,
    fontWeight: '700',
  },
  nameRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
  },
  name: { fontFamily: fonts.display, fontSize: 28, fontWeight: '700' },
  status: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  dot: { width: 8, height: 8, borderRadius: 4 },
  statusText: { fontFamily: fonts.bodyMedium, fontSize: 14, fontWeight: '600' },
  metaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 8,
  },
  price: { fontFamily: fonts.bodyMedium, fontSize: 16 },
  renews: { fontFamily: fonts.body, fontSize: 14 },
  credits: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    borderRadius: radii.md,
    borderWidth: 1,
    padding: spacing.md,
  },
  creditsMeta: { flex: 1, gap: 2 },
  creditsKicker: { fontFamily: fonts.body, fontSize: 12 },
  creditsValue: { fontFamily: fonts.display, fontSize: 26, fontWeight: '700' },
  creditsHint: { fontFamily: fonts.body, fontSize: 12 },
  buy: {
    borderWidth: 1.5,
    borderRadius: radii.md,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  buyText: { fontFamily: fonts.bodyMedium, fontSize: 14, fontWeight: '600' },
});
