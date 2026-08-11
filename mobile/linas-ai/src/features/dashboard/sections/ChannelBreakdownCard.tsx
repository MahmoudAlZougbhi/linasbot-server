import { Pressable, StyleSheet, Text, View } from 'react-native';

import { StatusChip } from '../../../components/StatusChip';
import { fonts, radii, spacing, useTheme } from '../../../theme';
import type { DashboardAction, TenantDashboard } from '../dashboardTypes';

type Channels = TenantDashboard['channels'];

type Props = {
  channels: Channels;
  onAction: (action: DashboardAction) => void;
};

function labelFor(platform: string, capability: string): string {
  const p = platform === 'instagram' ? 'Instagram' : platform === 'facebook' ? 'Facebook' : platform;
  const c = capability === 'dm' ? 'DMs' : 'Comments';
  return `${p} ${c}`;
}

function chipTone(operational: boolean, connected: boolean): 'ok' | 'warn' | 'soon' | 'neutral' {
  if (operational) return 'ok';
  if (connected) return 'warn';
  return 'soon';
}

export function ChannelBreakdownCard({ channels, onAction }: Props) {
  const { colors } = useTheme();
  if (channels.availability === 'error') {
    return (
      <View style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}>
        <Text style={[styles.title, { color: colors.text }]}>Channel breakdown</Text>
        <Text style={{ color: colors.danger, fontFamily: fonts.body }}>
          {channels.message || 'Channel status unavailable'}
        </Text>
      </View>
    );
  }

  const rows = channels.channels ?? [];
  return (
    <View style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}>
      <Text style={[styles.title, { color: colors.text }]}>Channel breakdown</Text>
      {!channels.membership_allows_comments ? (
        <Text style={{ color: colors.textMuted, fontFamily: fonts.body, fontSize: 13 }}>
          Comment automation is not included on the current plan.
        </Text>
      ) : null}
      <View style={styles.list}>
        {rows.map((row) => {
          const key = `${row.platform}-${row.capability}`;
          const statusLabel = row.operational
            ? 'Operational'
            : !row.connected
              ? 'Disconnected'
              : !row.membership_allows
                ? 'Plan locked'
                : row.blocker_code
                  ? 'Needs attention'
                  : 'Not ready';
          return (
            <View
              key={key}
              style={[styles.row, { borderColor: colors.borderSoft, backgroundColor: colors.surfaceAlt }]}
            >
              <View style={styles.rowHead}>
                <Text style={[styles.rowTitle, { color: colors.text }]}>
                  {labelFor(row.platform, row.capability)}
                </Text>
                <StatusChip label={statusLabel} tone={chipTone(row.operational, row.connected)} />
              </View>
              <Text style={{ color: colors.textMuted, fontFamily: fonts.body, fontSize: 12 }}>
                {row.connected ? 'Connected' : 'Not connected'}
                {row.enabled ? ' · Enabled' : ' · Disabled'}
                {row.interactions != null ? ` · ${row.interactions.toLocaleString()} interactions` : ''}
              </Text>
              {row.blocker_message ? (
                <Text style={{ color: colors.textDim, fontFamily: fonts.body, fontSize: 12, marginTop: 4 }}>
                  {row.blocker_message}
                </Text>
              ) : null}
              {row.action ? (
                <Pressable
                  onPress={() => onAction(row.action!)}
                  accessibilityRole="button"
                  accessibilityLabel={row.action.label}
                  style={{ marginTop: 6 }}
                >
                  <Text style={{ color: colors.accent, fontFamily: fonts.bodyMedium }}>{row.action.label}</Text>
                </Pressable>
              ) : null}
            </View>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { borderRadius: radii.lg, borderWidth: 1, padding: spacing.lg, gap: spacing.sm },
  title: { fontFamily: fonts.bodyMedium, fontSize: 16 },
  list: { gap: spacing.sm },
  row: { borderWidth: 1, borderRadius: radii.md, padding: spacing.md, gap: 4 },
  rowHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 },
  rowTitle: { fontFamily: fonts.bodyMedium, fontSize: 14, flex: 1 },
});
