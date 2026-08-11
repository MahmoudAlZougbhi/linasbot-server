import { StyleSheet, Text, View } from 'react-native';

import { fonts, radii, spacing, useTheme } from '../../../theme';
import type { TenantDashboard } from '../dashboardTypes';

type Dist = TenantDashboard['usage_distribution'];

const LABELS: Record<string, string> = {
  instagram_dm: 'Instagram DM',
  facebook_dm: 'Facebook DM',
  instagram_comments: 'Instagram Comments',
  facebook_comments: 'Facebook Comments',
  owner_copilot: 'Owner Copilot',
  content_management_ai: 'Content Management AI',
  other: 'Other',
};

type Props = { distribution: Dist };

export function UsageDistributionCard({ distribution }: Props) {
  const { colors } = useTheme();
  if (distribution.availability === 'error' || distribution.availability === 'unavailable') {
    return (
      <View style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}>
        <Text style={[styles.title, { color: colors.text }]}>Usage distribution</Text>
        <Text style={{ color: colors.textMuted, fontFamily: fonts.body }}>
          {distribution.message || 'Distribution unavailable'}
        </Text>
      </View>
    );
  }

  const items = distribution.items ?? [];
  const total = items.reduce((sum, item) => sum + item.interactions, 0) || 1;

  return (
    <View
      style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}
      accessibilityLabel={`Usage distribution by interaction count. Total ${total}`}
    >
      <Text style={[styles.title, { color: colors.text }]}>Usage distribution</Text>
      <Text style={{ color: colors.textDim, fontFamily: fonts.body, fontSize: 12 }}>
        Interaction count
        {distribution.credits_mode_available ? '' : ' · Credits mode unavailable'}
      </Text>
      {items.length === 0 ? (
        <Text style={{ color: colors.textMuted, fontFamily: fonts.body }}>No usage yet.</Text>
      ) : (
        items.map((item) => {
          const pct = Math.round((item.interactions / total) * 100);
          return (
            <View key={item.bucket} style={styles.row}>
              <View style={styles.rowHead}>
                <Text style={{ color: colors.text, fontFamily: fonts.bodyMedium, flex: 1 }}>
                  {LABELS[item.bucket] || item.bucket}
                </Text>
                <Text style={{ color: colors.textMuted, fontFamily: fonts.body }}>
                  {item.interactions.toLocaleString()} · {pct}%
                </Text>
              </View>
              <View style={[styles.track, { backgroundColor: colors.progressTrack }]}>
                <View
                  style={[
                    styles.fill,
                    { width: `${pct}%`, backgroundColor: colors.progressFill },
                  ]}
                />
              </View>
            </View>
          );
        })
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { borderRadius: radii.lg, borderWidth: 1, padding: spacing.lg, gap: spacing.sm },
  title: { fontFamily: fonts.bodyMedium, fontSize: 16 },
  row: { gap: 6 },
  rowHead: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  track: { height: 6, borderRadius: 999, overflow: 'hidden' },
  fill: { height: '100%', borderRadius: 999 },
});
