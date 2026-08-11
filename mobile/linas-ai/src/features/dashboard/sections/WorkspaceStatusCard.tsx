import { Pressable, StyleSheet, Text, View } from 'react-native';

import { StatusChip } from '../../../components/StatusChip';
import { fonts, radii, spacing, useTheme } from '../../../theme';
import type { DashboardAction } from '../dashboardTypes';

type Props = {
  title: string;
  explanation: string;
  state: string;
  action: DashboardAction | null | undefined;
  onAction?: (action: DashboardAction) => void;
};

function toneFor(state: string): 'ok' | 'warn' | 'soon' | 'neutral' {
  if (state === 'active') return 'ok';
  if (state === 'credits_low' || state === 'setup_needed') return 'warn';
  if (state === 'credits_depleted' || state === 'suspended' || state === 'subscription_issue') {
    return 'warn';
  }
  if (state === 'connection_issue' || state === 'temporarily_unavailable') return 'soon';
  return 'neutral';
}

export function WorkspaceStatusCard({ title, explanation, state, action, onAction }: Props) {
  const { colors } = useTheme();
  return (
    <View
      style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}
      accessibilityRole="summary"
      accessibilityLabel={`Workspace status ${title}`}
    >
      <View style={styles.head}>
        <Text style={[styles.title, { color: colors.text }]}>Workspace status</Text>
        <StatusChip label={title} tone={toneFor(state)} />
      </View>
      <Text style={[styles.body, { color: colors.textMuted }]}>{explanation}</Text>
      {action && onAction ? (
        <Pressable
          onPress={() => onAction(action)}
          accessibilityRole="button"
          accessibilityLabel={action.label}
          style={[styles.btn, { backgroundColor: colors.accentSoft }]}
        >
          <Text style={{ color: colors.accentDeep, fontFamily: fonts.bodyMedium }}>{action.label}</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: radii.lg,
    borderWidth: 1,
    padding: spacing.lg,
    gap: spacing.sm,
  },
  head: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  title: { fontFamily: fonts.bodyMedium, fontSize: 16 },
  body: { fontFamily: fonts.body, fontSize: 14, lineHeight: 20 },
  btn: {
    alignSelf: 'flex-start',
    borderRadius: radii.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    marginTop: spacing.xs,
  },
});
