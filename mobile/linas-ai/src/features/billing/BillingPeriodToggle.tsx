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
    <View style={styles.wrap} accessibilityRole="tablist">
      {(['monthly', 'yearly'] as const).map((p) => {
        const active = period === p;
        return (
          <Pressable
            key={p}
            onPress={() => {
              if (p === 'yearly') return;
              onChange(p);
            }}
            disabled={p === 'yearly'}
            style={[
              styles.tab,
              {
                borderColor: active ? colors.accent : colors.border,
                backgroundColor: colors.surface,
                opacity: p === 'yearly' ? 0.45 : 1,
              },
            ]}
            accessibilityRole="tab"
            accessibilityState={{ selected: active, disabled: p === 'yearly' }}
            accessibilityLabel={p === 'monthly' ? tr('subPeriodMonthly') : tr('subPeriodYearly')}
          >
            <Text
              style={[
                styles.label,
                { color: active ? colors.accent : colors.textMuted },
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
    gap: 10,
  },
  tab: {
    flex: 1,
    borderRadius: radii.md,
    borderWidth: 1.5,
    paddingVertical: 12,
    alignItems: 'center',
  },
  label: { fontFamily: fonts.bodyMedium, fontSize: 15, fontWeight: '600' },
});
