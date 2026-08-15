import { Ionicons } from '@expo/vector-icons';
import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { useI18n } from '../../../i18n/LanguageContext';
import { fonts, spacing, useTheme } from '../../../theme';
import { DASH_CARD_RADIUS } from '../dashboardChrome';
import type { DashboardPeriodSelection } from '../dashboardFormat';
import { formatDashboardRangeLabel, isAllTimePeriod } from '../dashboardFormat';
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
  const rangeLabel = isAllTimePeriod(period)
    ? tr('dashAllTime')
    : formatDashboardRangeLabel(rangeStart, rangeEnd, locale);
  const subtitle = isAllTimePeriod(period)
    ? tr('dashAllTime')
    : period.kind === 'custom'
      ? tr('dashCustomRange')
      : period.id === 'today'
        ? tr('dashToday')
        : period.id === 'last_month'
          ? tr('dashLastMonth')
          : period.id === 'last_6m'
            ? tr('dashLast6Months')
            : tr('dashLastYear');

  return (
    <>
      <Pressable
        onPress={() => setSheetOpen(true)}
        accessibilityRole="button"
        accessibilityLabel={tr('dashSelectRange')}
        style={({ pressed }) => [
          styles.card,
          { backgroundColor: colors.surface, borderColor: colors.border },
          pressed && styles.pressed,
        ]}
      >
        <Ionicons name="calendar-outline" size={20} color={colors.text} />
        <View style={styles.pillText}>
          <Text style={[styles.range, { color: colors.text }]}>{rangeLabel}</Text>
          <Text style={[styles.sub, { color: colors.textMuted }]}>{subtitle}</Text>
        </View>
        <Ionicons name="chevron-down" size={16} color={colors.textDim} />
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
  card: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    borderWidth: 1,
    borderRadius: DASH_CARD_RADIUS,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
  },
  pressed: { opacity: 0.85 },
  pillText: { flex: 1, gap: 2 },
  range: { fontFamily: fonts.body, fontSize: 14 },
  sub: { fontFamily: fonts.body, fontSize: 13 },
});
