import { Pressable, StyleSheet, Text, View } from 'react-native';

import { useI18n } from '../../i18n/LanguageContext';
import { fonts, radii, spacing, useTheme } from '../../theme';
import { useBillingData } from '../billing/useBillingData';

type Props = {
  showUpgrade: boolean;
  onBuyCredits: () => void;
  onUpgrade: () => void;
};

export function CreditsPausedBanner({ showUpgrade, onBuyCredits, onUpgrade }: Props) {
  const { colors } = useTheme();
  const { tr } = useI18n();
  const { messageBillingActive } = useBillingData();
  return (
    <View
      style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}
      accessibilityRole="alert"
    >
      <Text style={[styles.title, { color: colors.text }]}>{tr('chatLeftoverCreditsPausedTitle')}</Text>
      <Text style={[styles.body, { color: colors.textMuted }]}>{tr('chatLeftoverCreditsPausedBody')}</Text>
      <View style={styles.row}>
        {showUpgrade ? (
          <Pressable onPress={onUpgrade} style={styles.outline} accessibilityRole="button">
            <Text style={[styles.outlineText, { color: colors.accent }]}>{tr('subUpgradePlan')}</Text>
          </Pressable>
        ) : null}
        {messageBillingActive ? null : (
          <Pressable
            onPress={onBuyCredits}
            style={[styles.fill, { backgroundColor: colors.accent }]}
            accessibilityRole="button"
          >
            <Text style={styles.fillText}>{tr('chatAddLeftoverCredits')}</Text>
          </Pressable>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    marginHorizontal: spacing.md,
    marginBottom: spacing.sm,
    borderWidth: 1,
    borderRadius: radii.lg,
    padding: spacing.md,
    gap: spacing.sm,
  },
  title: { fontFamily: fonts.bodyMedium, fontSize: 15 },
  body: { fontFamily: fonts.body, fontSize: 13, lineHeight: 18 },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, marginTop: 4 },
  outline: {
    borderWidth: 1,
    borderRadius: radii.md,
    paddingHorizontal: spacing.md,
    paddingVertical: 8,
    borderColor: 'rgba(13,148,136,0.45)',
  },
  outlineText: { fontFamily: fonts.bodyMedium, fontSize: 13 },
  fill: { borderRadius: radii.md, paddingHorizontal: spacing.md, paddingVertical: 8 },
  fillText: { color: '#FFFFFF', fontFamily: fonts.bodyMedium, fontSize: 13 },
});
