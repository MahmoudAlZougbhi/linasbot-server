import { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Modal,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { AppIcon, feather, ion } from '../../components/AppIcon';
import type { StringKey } from '../../i18n';
import { fonts, radii, spacing, useTheme } from '../../theme';
import {
  CREDIT_PACK_CATALOG_USD,
  CREDIT_PACK_ORDER,
  DEFAULT_CREDIT_PACK,
  type CreditPackId,
} from './appleProductIds';
import type { CreditStorePrice } from './storePricing';

type Props = {
  visible: boolean;
  prices: CreditStorePrice[];
  purchasing: boolean;
  locale: string;
  tr: (key: StringKey) => string;
  onBuy: (credits: CreditPackId) => void;
  onClose: () => void;
};

export function BuyCreditsSheet({
  visible,
  prices,
  purchasing,
  locale,
  tr,
  onBuy,
  onClose,
}: Props) {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const [selected, setSelected] = useState<CreditPackId>(DEFAULT_CREDIT_PACK);
  const byCredits = new Map(prices.map((p) => [p.credits, p]));

  useEffect(() => {
    if (visible) setSelected(DEFAULT_CREDIT_PACK);
  }, [visible]);

  const store = byCredits.get(selected);
  const available = Boolean(store?.available && store.localizedPrice);
  const priceLabel = available
    ? store!.localizedPrice
    : formatUsd(CREDIT_PACK_CATALOG_USD[selected]);
  const creditsLabel = selected.toLocaleString(locale);
  const cta = tr('subBuyCreditsCta')
    .replace('{n}', creditsLabel)
    .replace('{price}', priceLabel);

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={[styles.scrim, { backgroundColor: colors.overlay }]} onPress={onClose}>
        <Pressable
          style={[
            styles.sheet,
            { backgroundColor: colors.surface, paddingBottom: Math.max(insets.bottom, 16) + 8 },
          ]}
          onPress={(e) => e.stopPropagation()}
        >
          <View style={[styles.handle, { backgroundColor: colors.border }]} />
          <View style={styles.head}>
            <View style={styles.headCopy}>
              <Text style={[styles.title, { color: colors.text }]}>{tr('subBuyCredits')}</Text>
              <Text style={[styles.sub, { color: colors.textMuted }]}>{tr('subChooseCreditPack')}</Text>
            </View>
            <Pressable
              onPress={onClose}
              accessibilityRole="button"
              accessibilityLabel={tr('usersClose')}
              hitSlop={8}
            >
              <AppIcon icon={feather('x')} size={22} color={colors.textMuted} />
            </Pressable>
          </View>

          <View style={styles.packs}>
            {CREDIT_PACK_ORDER.map((credits) => {
              const row = byCredits.get(credits);
              const on = credits === selected;
              const rowPrice =
                row?.available && row.localizedPrice
                  ? row.localizedPrice
                  : formatUsd(CREDIT_PACK_CATALOG_USD[credits]);
              return (
                <Pressable
                  key={credits}
                  onPress={() => setSelected(credits)}
                  accessibilityRole="radio"
                  accessibilityState={{ selected: on }}
                  style={[
                    styles.pack,
                    {
                      borderColor: on ? colors.accent : colors.border,
                      borderWidth: on ? 2 : 1,
                    },
                  ]}
                >
                  <View
                    style={[
                      styles.radio,
                      { borderColor: on ? colors.accent : colors.textDim },
                    ]}
                  >
                    {on ? <View style={[styles.radioDot, { backgroundColor: colors.accent }]} /> : null}
                  </View>
                  <Text style={[styles.packCredits, { color: on ? colors.accent : colors.text }]}>
                    {credits.toLocaleString(locale)} {tr('subCreditsUnit')}
                  </Text>
                  <Text style={[styles.packPrice, { color: on ? colors.accent : colors.text }]}>
                    {rowPrice}
                  </Text>
                </Pressable>
              );
            })}
          </View>

          <View style={[styles.info, { backgroundColor: colors.banner }]}>
            <AppIcon icon={ion('information-circle')} size={18} color={colors.accent} />
            <Text style={[styles.infoText, { color: colors.textMuted }]}>
              {tr('subPurchasedNoExpire')}
            </Text>
          </View>

          <Pressable
            onPress={() => onBuy(selected)}
            disabled={!available || purchasing}
            accessibilityRole="button"
            accessibilityState={{ disabled: !available || purchasing }}
            style={({ pressed }) => [
              styles.cta,
              {
                backgroundColor: available ? colors.accent : colors.surfaceAlt,
                opacity: pressed && available ? 0.88 : 1,
              },
            ]}
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
                {cta}
              </Text>
            )}
          </Pressable>
          <Text style={[styles.legal, { color: colors.textMuted }]}>{tr('subFooterStore')}</Text>
          <Pressable
            onPress={onClose}
            accessibilityRole="button"
            accessibilityLabel={tr('subCancel')}
            style={({ pressed }) => [
              styles.cancel,
              { borderColor: colors.accent, opacity: pressed ? 0.7 : 1 },
            ]}
          >
            <Text style={[styles.cancelText, { color: colors.accent }]}>{tr('subCancel')}</Text>
          </Pressable>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

function formatUsd(amount: number): string {
  return `$${amount.toFixed(2)}`;
}

const styles = StyleSheet.create({
  scrim: { flex: 1, justifyContent: 'flex-end' },
  sheet: {
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    paddingHorizontal: spacing.lg,
    paddingTop: 8,
    gap: 12,
  },
  handle: {
    alignSelf: 'center',
    width: 40,
    height: 4,
    borderRadius: 2,
    marginBottom: 4,
  },
  head: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between' },
  headCopy: { gap: 2 },
  title: { fontFamily: fonts.display, fontSize: 22, fontWeight: '700' },
  sub: { fontFamily: fonts.body, fontSize: 14 },
  packs: { gap: 8 },
  pack: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    borderRadius: radii.md,
    paddingHorizontal: 14,
    paddingVertical: 14,
  },
  radio: {
    width: 22,
    height: 22,
    borderRadius: 11,
    borderWidth: 2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  radioDot: { width: 10, height: 10, borderRadius: 5 },
  packCredits: { flex: 1, fontFamily: fonts.bodyMedium, fontSize: 16 },
  packPrice: { fontFamily: fonts.bodyMedium, fontSize: 16 },
  info: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    borderRadius: radii.md,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  infoText: { flex: 1, fontFamily: fonts.body, fontSize: 13 },
  cta: {
    borderRadius: radii.md,
    paddingVertical: 16,
    alignItems: 'center',
  },
  ctaText: { fontFamily: fonts.bodyMedium, fontSize: 16, fontWeight: '700' },
  legal: { fontFamily: fonts.body, fontSize: 11, textAlign: 'center', lineHeight: 15 },
  cancel: {
    borderWidth: 1.5,
    borderRadius: radii.md,
    paddingVertical: 14,
    alignItems: 'center',
  },
  cancelText: { fontFamily: fonts.bodyMedium, fontSize: 16, fontWeight: '600' },
});
