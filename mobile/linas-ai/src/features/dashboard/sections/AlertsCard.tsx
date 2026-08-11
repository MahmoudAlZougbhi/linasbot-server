import { Pressable, StyleSheet, Text, View } from 'react-native';

import { StatusChip } from '../../../components/StatusChip';
import { fonts, radii, spacing, useTheme } from '../../../theme';
import type { DashboardAction, TenantDashboard } from '../dashboardTypes';

type Alert = TenantDashboard['alerts'][number];

type Props = {
  alerts: Alert[];
  onAction: (action: DashboardAction) => void;
};

function tone(severity: string): 'ok' | 'warn' | 'soon' | 'neutral' {
  if (severity === 'critical') return 'warn';
  if (severity === 'warning') return 'soon';
  return 'neutral';
}

export function AlertsCard({ alerts, onAction }: Props) {
  const { colors } = useTheme();
  return (
    <View style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}>
      <Text style={[styles.title, { color: colors.text }]}>Alerts</Text>
      {alerts.length === 0 ? (
        <Text style={{ color: colors.textMuted, fontFamily: fonts.body }}>
          No attention items right now.
        </Text>
      ) : (
        alerts.map((alert) => (
          <View
            key={`${alert.reason_code}-${alert.timestamp}`}
            style={[styles.row, { borderColor: colors.borderSoft }]}
          >
            <View style={styles.head}>
              <Text style={[styles.rowTitle, { color: colors.text }]}>{alert.title}</Text>
              <StatusChip label={alert.severity} tone={tone(alert.severity)} />
            </View>
            <Text style={{ color: colors.textMuted, fontFamily: fonts.body, fontSize: 13 }}>
              {alert.explanation}
            </Text>
            <Text style={{ color: colors.textDim, fontFamily: fonts.body, fontSize: 11 }}>
              {new Date(alert.timestamp).toLocaleString()}
            </Text>
            {alert.action ? (
              <Pressable
                onPress={() => onAction(alert.action!)}
                accessibilityRole="button"
                accessibilityLabel={alert.action.label}
              >
                <Text style={{ color: colors.accent, fontFamily: fonts.bodyMedium }}>
                  {alert.action.label}
                </Text>
              </Pressable>
            ) : null}
          </View>
        ))
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { borderRadius: radii.lg, borderWidth: 1, padding: spacing.lg, gap: spacing.md },
  title: { fontFamily: fonts.bodyMedium, fontSize: 16 },
  row: { borderTopWidth: 1, paddingTop: spacing.md, gap: 4 },
  head: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 },
  rowTitle: { fontFamily: fonts.bodyMedium, fontSize: 14, flex: 1 },
});
