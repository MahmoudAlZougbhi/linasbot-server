import { Ionicons } from '@expo/vector-icons';
import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { useI18n } from '../../../i18n/LanguageContext';
import { fonts, radii, spacing, useTheme } from '../../../theme';
import type { DashboardPeriodSelection } from '../dashboardFormat';
import { formatDashboardRangeLabel } from '../dashboardFormat';
import { DashboardDateRangeSheet } from './DashboardDateRangeSheet';

type Props = {
  period: DashboardPeriodSelection;
  rangeStart: string;
  rangeEnd: string;
  onPeriodChange: (next: DashboardPeriodSelection) => void;
};

export function DashboardHeader({
  period,
  rangeStart,
  rangeEnd,
  onPeriodChange,
}: Props) {
  const { colors } = useTheme();
  const { tr, language } = useI18n();
  const [sheetOpen, setSheetOpen] = useState(false);
  const locale = language === 'ar' ? 'ar' : language === 'fr' ? 'fr' : 'en';
  const rangeLabel = formatDashboardRangeLabel(rangeStart, rangeEnd, locale);
  const subtitle =
    period.kind === 'custom'
      ? tr('dashCustomRange')
      : period.id === '7d'
        ? tr('dashLast7Days')
        : period.id === '30d'
          ? tr('dashLast30Days')
          : tr('dashBillingPeriod');

  return (
    <>
      <Pressable
        onPress={() => setSheetOpen(true)}
        accessibilityRole="button"
        accessibilityLabel={tr('dashSelectRange')}
        style={({ pressed }) => [
          styles.pill,
          { backgroundColor: colors.surface, borderColor: colors.border },
          pressed && styles.pressed,
        ]}
      >
        <View style={[styles.calIcon, { backgroundColor: colors.surfaceAlt }]}>
          <Ionicons name="calendar-outline" size={18} color={colors.accent} />
        </View>
        <View style={styles.pillText}>
          <Text style={[styles.range, { color: colors.text }]}>{rangeLabel}</Text>
          <Text style={[styles.sub, { color: colors.textMuted }]}>{subtitle}</Text>
        </View>
        <Ionicons name="chevron-down" size={18} color={colors.textDim} />
      </Pressable>

      <DashboardDateRangeSheet
        open={sheetOpen}
        period={period}
        onClose={() => setSheetOpen(false)}
        onApply={(next) => {
          onPeriodChange(next);
          setSheetOpen(false);
        }}
      />
    </>
  );
}

const styles = StyleSheet.create({
  pill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    borderWidth: 1,
    borderRadius: radii.pill,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm + 2,
    marginBottom: spacing.md,
  },
  pressed: { opacity: 0.85 },
  calIcon: {
    width: 36,
    height: 36,
    borderRadius: 18,
    alignItems: 'center',
    justifyContent: 'center',
  },
  pillText: { flex: 1, gap: 2 },
  range: { fontFamily: fonts.bodyMedium, fontSize: 15 },
  sub: { fontFamily: fonts.body, fontSize: 12 },
});
