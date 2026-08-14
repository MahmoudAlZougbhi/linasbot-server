import { StyleSheet, Text, View } from 'react-native';

import type { StringKey } from '../../i18n';
import { fonts, radii, spacing, useTheme } from '../../theme';
import { PlanFeatureIcon } from './PlanFeatureIcon';
import {
  currentPlanIncludeIcons,
  type IncludedRow,
} from './planEntitlements';

type Props = {
  title: string;
  rows: IncludedRow[];
  tr: (key: StringKey) => string;
  locale: string;
  variant: 'current' | 'choose';
};

export function PlanIncludedList({ title, rows, tr, locale, variant }: Props) {
  const { colors } = useTheme();
  const framed = variant === 'current';
  return (
    <View style={styles.wrap}>
      <Text style={[styles.title, { color: colors.text }]}>{title}</Text>
      <View
        style={
          framed
            ? [styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]
            : undefined
        }
      >
        {rows.map((row, index) => (
          <View
            key={row.id}
            style={[
              styles.row,
              !framed && styles.rowFlush,
              index < rows.length - 1 && {
                borderBottomWidth: StyleSheet.hairlineWidth,
                borderBottomColor: colors.border,
              },
            ]}
          >
            <PlanFeatureIcon
              name={variant === 'current' ? currentPlanIncludeIcons(row) : row.icon}
              color={colors.accent}
            />
            <Text style={[styles.label, { color: colors.text }]}>
              {labelFor(row, tr, locale)}
            </Text>
          </View>
        ))}
      </View>
    </View>
  );
}

export function labelFor(
  row: IncludedRow,
  tr: (key: StringKey) => string,
  locale: string,
): string {
  const text = tr(row.labelKey);
  if (row.count == null) return text;
  return text.replace('{n}', row.count.toLocaleString(locale));
}

const styles = StyleSheet.create({
  wrap: { gap: spacing.sm },
  title: { fontFamily: fonts.bodyMedium, fontSize: 16, fontWeight: '700' },
  card: {
    borderRadius: radii.lg,
    borderWidth: 1,
    overflow: 'hidden',
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingHorizontal: spacing.lg,
    paddingVertical: 14,
  },
  rowFlush: { paddingHorizontal: 0 },
  label: { flex: 1, fontFamily: fonts.body, fontSize: 15, lineHeight: 20 },
});
