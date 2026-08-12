import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';

import type { StringKey } from '../../i18n';
import { fonts, radii, spacing, useTheme } from '../../theme';
import type { CreditPackId } from './appleProductIds';
import { CREDIT_PACK_ORDER } from './appleProductIds';
import type { CreditStorePrice } from './storePricing';

type Props = {
  tr: (key: StringKey) => string;
  prices: CreditStorePrice[];
  purchasing: boolean;
  onBuy: (credits: CreditPackId) => void;
  locale: string;
};

export function CreditPacksSection({ tr, prices, purchasing, onBuy, locale }: Props) {
  const { colors } = useTheme();
  const byCredits = new Map(prices.map((p) => [p.credits, p]));

  return (
    <View style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}>
      <Text style={[styles.title, { color: colors.accentDeep }]}>{tr('subCreditsPacksTitle')}</Text>
      <Text style={[styles.sub, { color: colors.textMuted }]}>{tr('subCreditsPacksBody')}</Text>
      {CREDIT_PACK_ORDER.map((credits) => {
        const price = byCredits.get(credits);
        const available = Boolean(price?.available && price.localizedPrice);
        return (
          <View
            key={credits}
            style={[styles.row, { borderColor: colors.border }]}
          >
            <View style={styles.meta}>
              <Text style={[styles.credits, { color: colors.text }]}>
                {credits.toLocaleString(locale)} {tr('subCreditsUnit')}
              </Text>
              <Text style={[styles.price, { color: available ? colors.text : colors.textDim }]}>
                {available ? price!.localizedPrice : tr('subPriceUnavailable')}
              </Text>
            </View>
            <Pressable
              onPress={() => onBuy(credits)}
              disabled={!available || purchasing}
              style={({ pressed }) => [
                styles.cta,
                {
                  backgroundColor: available ? colors.accent : colors.surfaceAlt,
                  opacity: pressed && available ? 0.85 : 1,
                },
              ]}
              accessibilityRole="button"
              accessibilityState={{ disabled: !available || purchasing }}
              accessibilityLabel={tr('subBuyCredits')}
            >
              {purchasing ? (
                <ActivityIndicator color={colors.onAccent} />
              ) : (
                <Text
                  style={[
                    styles.ctaText,
                    { color: available ? colors.onAccent : colors.textMuted },
                  ]}
                >
                  {tr('subBuyCredits')}
                </Text>
              )}
            </Pressable>
          </View>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: radii.lg,
    borderWidth: 1,
    padding: spacing.lg,
    gap: spacing.sm,
  },
  title: { fontFamily: fonts.display, fontSize: 18 },
  sub: { fontFamily: fonts.body, fontSize: 13, lineHeight: 18, marginBottom: 4 },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
    borderTopWidth: StyleSheet.hairlineWidth,
    paddingTop: spacing.sm,
  },
  meta: { flex: 1, gap: 2 },
  credits: { fontFamily: fonts.bodyMedium, fontSize: 15 },
  price: { fontFamily: fonts.body, fontSize: 14 },
  cta: {
    borderRadius: radii.md,
    paddingHorizontal: 14,
    paddingVertical: 10,
    minWidth: 88,
    alignItems: 'center',
  },
  ctaText: { fontFamily: fonts.bodyMedium, fontSize: 13 },
});
