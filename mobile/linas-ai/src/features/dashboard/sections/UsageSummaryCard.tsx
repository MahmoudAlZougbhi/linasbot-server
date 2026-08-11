import { StyleSheet, Text, View } from 'react-native';

import { fonts, radii, spacing, useTheme } from '../../../theme';
import type { TenantDashboard } from '../dashboardTypes';
import { InteractionSparkline } from './InteractionSparkline';

type Usage = TenantDashboard['usage_summary'];

type Props = { usage: Usage; periodLabel: string };

function Stat({ label, value }: { label: string; value: string }) {
  const { colors } = useTheme();
  return (
    <View style={styles.stat}>
      <Text style={[styles.statLabel, { color: colors.textDim }]}>{label}</Text>
      <Text style={[styles.statValue, { color: colors.text }]}>{value}</Text>
    </View>
  );
}

function fmt(n: number | null | undefined): string {
  if (n == null) return 'Unavailable';
  return n.toLocaleString();
}

export function UsageSummaryCard({ usage, periodLabel }: Props) {
  const { colors } = useTheme();
  if (usage.availability === 'error') {
    return (
      <View style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}>
        <Text style={[styles.title, { color: colors.text }]}>Usage summary</Text>
        <Text style={{ color: colors.danger, fontFamily: fonts.body }}>
          {usage.message || 'Usage unavailable'}
        </Text>
      </View>
    );
  }
  if (usage.availability === 'empty') {
    return (
      <View style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}>
        <Text style={[styles.title, { color: colors.text }]}>Usage summary</Text>
        <Text style={{ color: colors.textMuted, fontFamily: fonts.body }}>
          No AI interactions yet for {periodLabel}.
        </Text>
      </View>
    );
  }

  const rate =
    typeof usage.success_rate === 'number' ? `${Math.round(usage.success_rate * 100)}%` : 'Unavailable';

  return (
    <View
      style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}
      accessibilityLabel={`Usage summary for ${periodLabel}. Total interactions ${fmt(usage.total_interactions)}`}
    >
      <Text style={[styles.title, { color: colors.text }]}>Usage summary</Text>
      <Text style={{ color: colors.textDim, fontFamily: fonts.body, fontSize: 12 }}>{periodLabel}</Text>
      <View style={styles.grid}>
        <Stat label="Total AI interactions" value={fmt(usage.total_interactions)} />
        <Stat label="Success rate" value={rate} />
        <Stat label="Instagram DMs" value={fmt(usage.instagram_dms)} />
        <Stat label="Facebook DMs" value={fmt(usage.facebook_dms)} />
        <Stat label="Instagram comments" value={fmt(usage.instagram_comments)} />
        <Stat label="Facebook comments" value={fmt(usage.facebook_comments)} />
        <Stat label="Owner Copilot" value={fmt(usage.owner_copilot)} />
        <Stat label="Content Management AI" value={fmt(usage.content_management_ai)} />
        <Stat label="Failed / handoffs" value={fmt(usage.failed_interactions)} />
      </View>
      {usage.time_series && usage.time_series.length > 0 ? (
        <InteractionSparkline points={usage.time_series} />
      ) : null}
      {usage.credits_by_bucket_note ? (
        <Text style={{ color: colors.textDim, fontFamily: fonts.body, fontSize: 11, marginTop: 6 }}>
          Credits consumed by channel: unavailable from current ledger.
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { borderRadius: radii.lg, borderWidth: 1, padding: spacing.lg, gap: spacing.sm },
  title: { fontFamily: fonts.bodyMedium, fontSize: 16 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.md, marginTop: 4 },
  stat: { width: '45%', gap: 2 },
  statLabel: { fontFamily: fonts.body, fontSize: 11 },
  statValue: { fontFamily: fonts.bodyMedium, fontSize: 16 },
});
