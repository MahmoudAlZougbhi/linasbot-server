import { Pressable, StyleSheet, Text, View } from 'react-native';

import type { StringKey } from '../../i18n';
import { fonts, radii, spacing, useTheme } from '../../theme';
import type { BillingPeriod } from './appleProductIds';

type Props = {
  period: BillingPeriod;
  onChange: (period: BillingPeriod) => void;
  tr: (key: StringKey) => string;
};

export function BillingPeriodToggle({ period, onChange, tr }: Props) {
  const { colors } = useTheme();
  return (
    <View
      style={[styles.wrap, { backgroundColor: colors.surfaceAlt, borderColor: colors.border }]}
      accessibilityRole="tablist"
    >
      {(['monthly', 'yearly'] as const).map((p) => {
        const active = period === p;
        return (
          <Pressable
            key={p}
            onPress={() => onChange(p)}
            style={[
              styles.tab,
              active && { backgroundColor: colors.surface, borderColor: colors.accent },
            ]}
            accessibilityRole="tab"
            accessibilityState={{ selected: active }}
            accessibilityLabel={p === 'monthly' ? tr('subPeriodMonthly') : tr('subPeriodYearly')}
          >
            <Text
              style={[
                styles.label,
                { color: active ? colors.accentDeep : colors.textMuted },
              ]}
            >
              {p === 'monthly' ? tr('subPeriodMonthly') : tr('subPeriodYearly')}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    flexDirection: 'row',
    borderRadius: radii.md,
    borderWidth: 1,
    padding: 4,
    gap: 4,
  },
  tab: {
    flex: 1,
    borderRadius: radii.sm,
    borderWidth: 1,
    borderColor: 'transparent',
    paddingVertical: spacing.sm,
    alignItems: 'center',
  },
  label: { fontFamily: fonts.bodyMedium, fontSize: 14 },
});
