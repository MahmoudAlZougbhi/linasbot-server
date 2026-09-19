import { Pressable, StyleSheet, Text, View } from 'react-native';

import { useI18n } from '../../i18n/LanguageContext';
import { fonts, radii, spacing, useTheme } from '../../theme';

type Props = {
  units: number;
  message: string;
  onConfirm: () => void;
  onDismiss: () => void;
};

export function BillingConfirmBanner({ units, message, onConfirm, onDismiss }: Props) {
  const { colors } = useTheme();
  const { tr } = useI18n();
  return (
    <View
      style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}
      accessibilityRole="alert"
    >
      <Text style={[styles.title, { color: colors.text }]}>{tr('chatBillingConfirmTitle')}</Text>
      <Text style={[styles.body, { color: colors.textMuted }]}>
        {message || tr('chatBillingConfirmBody').replace('{n}', String(units))}
      </Text>
      <View style={styles.row}>
        <Pressable onPress={onDismiss} style={styles.outline} accessibilityRole="button">
          <Text style={[styles.outlineText, { color: colors.accent }]}>{tr('subCancel')}</Text>
        </Pressable>
        <Pressable
          onPress={onConfirm}
          style={[styles.fill, { backgroundColor: colors.accent }]}
          accessibilityRole="button"
        >
          <Text style={styles.fillText}>{tr('chatBillingConfirmCta')}</Text>
        </Pressable>
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
