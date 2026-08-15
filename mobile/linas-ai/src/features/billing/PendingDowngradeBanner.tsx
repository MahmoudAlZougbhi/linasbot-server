import { Pressable, StyleSheet, Text, View } from 'react-native';

import type { StringKey } from '../../i18n';
import { fonts, radii, spacing, useTheme } from '../../theme';
import type { PendingDowngrade } from './planChangeApi';
import { PLAN_NAME_KEY } from './planEntitlements';
import type { PlanId } from './planCatalog';

type Props = {
  pending: PendingDowngrade;
  locale: string;
  tr: (key: StringKey) => string;
  onCancel: () => void;
  canceling: boolean;
};

export function PendingDowngradeBanner({
  pending,
  locale,
  tr,
  onCancel,
  canceling,
}: Props) {
  const { colors } = useTheme();
  const date = new Date(pending.effectiveAt * 1000).toLocaleDateString(locale, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
  const planName = tr(PLAN_NAME_KEY[pending.planId as PlanId]);
  const message = tr('subPendingDowngradeBody')
    .replace('{date}', date)
    .replace('{plan}', planName);

  return (
    <View style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.warning }]}>
      <Text style={[styles.title, { color: colors.text }]}>{tr('subPendingDowngradeTitle')}</Text>
      <Text style={[styles.body, { color: colors.textMuted }]}>{message}</Text>
      <Pressable
        onPress={onCancel}
        disabled={canceling}
        accessibilityRole="button"
        accessibilityLabel={tr('subCancelPendingDowngrade')}
        style={({ pressed }) => [
          styles.cancel,
          {
            borderColor: colors.border,
            opacity: pressed || canceling ? 0.7 : 1,
          },
        ]}
      >
        <Text style={[styles.cancelText, { color: colors.text }]}>
          {canceling ? tr('subPurchasePending') : tr('subCancelPendingDowngrade')}
        </Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderWidth: 1,
    borderRadius: radii.md,
    padding: spacing.md,
    gap: 8,
  },
  title: { fontFamily: fonts.bodyMedium, fontSize: 15, fontWeight: '700' },
  body: { fontFamily: fonts.body, fontSize: 14, lineHeight: 20 },
  cancel: {
    alignSelf: 'flex-start',
    borderWidth: 1,
    borderRadius: radii.md,
    paddingHorizontal: 12,
    paddingVertical: 8,
    marginTop: 4,
  },
  cancelText: { fontFamily: fonts.bodyMedium, fontSize: 14, fontWeight: '600' },
});
