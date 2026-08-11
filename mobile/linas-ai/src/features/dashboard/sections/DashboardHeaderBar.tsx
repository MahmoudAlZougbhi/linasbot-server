import { Pressable, StyleSheet, Text, View } from 'react-native';

import { fonts, radii, spacing, useTheme } from '../../../theme';
import type { DashboardPeriodId } from '../dashboardTypes';

type Props = {
  workspaceName: string;
  lastUpdated: string | null;
  period: DashboardPeriodId;
  onPeriodChange: (period: DashboardPeriodId) => void;
  onRefresh: () => void;
  refreshing: boolean;
  stale: boolean;
};

const PERIODS: { id: DashboardPeriodId; label: string }[] = [
  { id: 'billing', label: 'Billing' },
  { id: '7d', label: '7 days' },
  { id: '30d', label: '30 days' },
];

export function DashboardHeaderBar({
  workspaceName,
  lastUpdated,
  period,
  onPeriodChange,
  onRefresh,
  refreshing,
  stale,
}: Props) {
  const { colors } = useTheme();
  return (
    <View style={styles.wrap}>
      <View style={styles.row}>
        <View style={{ flex: 1 }}>
          <Text style={[styles.workspace, { color: colors.text }]} numberOfLines={2}>
            {workspaceName}
          </Text>
          <Text style={[styles.meta, { color: colors.textMuted }]}>
            {stale ? 'Showing last successful snapshot · ' : ''}
            {lastUpdated ? `Updated ${lastUpdated}` : 'Not updated yet'}
          </Text>
        </View>
        <Pressable
          onPress={onRefresh}
          accessibilityRole="button"
          accessibilityLabel="Refresh dashboard"
          style={[styles.refresh, { borderColor: colors.border, backgroundColor: colors.surface }]}
        >
          <Text style={{ color: colors.accent, fontFamily: fonts.bodyMedium }}>
            {refreshing ? '…' : 'Refresh'}
          </Text>
        </Pressable>
      </View>
      <View style={styles.periods} accessibilityRole="tablist">
        {PERIODS.map((p) => {
          const active = p.id === period;
          return (
            <Pressable
              key={p.id}
              onPress={() => onPeriodChange(p.id)}
              accessibilityRole="tab"
              accessibilityState={{ selected: active }}
              accessibilityLabel={p.label}
              style={[
                styles.periodChip,
                {
                  backgroundColor: active ? colors.accentSoft : colors.surface,
                  borderColor: active ? colors.accent : colors.border,
                },
              ]}
            >
              <Text
                style={{
                  color: active ? colors.accentDeep : colors.textMuted,
                  fontFamily: fonts.bodyMedium,
                  fontSize: 13,
                }}
              >
                {p.label}
              </Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: spacing.sm, marginBottom: spacing.md },
  row: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  workspace: { fontFamily: fonts.bodyMedium, fontSize: 16 },
  meta: { fontFamily: fonts.body, fontSize: 12, marginTop: 2 },
  refresh: {
    borderWidth: 1,
    borderRadius: radii.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  periods: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  periodChip: {
    borderWidth: 1,
    borderRadius: radii.pill,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs + 2,
  },
});
