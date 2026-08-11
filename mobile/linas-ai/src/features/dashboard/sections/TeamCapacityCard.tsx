import { Pressable, StyleSheet, Text, View } from 'react-native';

import { fonts, radii, spacing, useTheme } from '../../../theme';
import type { TenantDashboard } from '../dashboardTypes';

type Team = TenantDashboard['team_capacity'];

type Props = { team: Team; onManageUsers: () => void };

export function TeamCapacityCard({ team, onManageUsers }: Props) {
  const { colors } = useTheme();
  if (team.availability === 'error') {
    return (
      <View style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}>
        <Text style={[styles.title, { color: colors.text }]}>Team capacity</Text>
        <Text style={{ color: colors.danger, fontFamily: fonts.body }}>
          {team.message || 'Team data unavailable'}
        </Text>
      </View>
    );
  }

  const seatsLabel = team.additional_seats_unlimited
    ? 'Unlimited'
    : team.additional_seat_allowance == null
      ? 'Unavailable'
      : String(team.additional_seat_allowance);
  const remainingLabel = team.additional_seats_unlimited
    ? 'Unlimited'
    : team.remaining_seats == null
      ? 'Unavailable'
      : String(team.remaining_seats);

  return (
    <View style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}>
      <Text style={[styles.title, { color: colors.text }]}>Team capacity</Text>
      <Text style={{ color: colors.textMuted, fontFamily: fonts.body }}>
        Owner: {team.owner?.name || team.owner?.email || 'Unavailable'}
      </Text>
      <Text style={{ color: colors.textMuted, fontFamily: fonts.body }}>
        Additional users: {team.active_additional_users ?? 'Unavailable'}
      </Text>
      <Text style={{ color: colors.textMuted, fontFamily: fonts.body }}>
        Pending invitations: {team.pending_invitations ?? 0}
      </Text>
      {team.pending_invitations_note ? (
        <Text style={{ color: colors.textDim, fontFamily: fonts.body, fontSize: 11 }}>
          {team.pending_invitations_note}
        </Text>
      ) : null}
      <Text style={{ color: colors.textMuted, fontFamily: fonts.body }}>
        Seat allowance: {seatsLabel} · Remaining: {remainingLabel}
      </Text>
      <Pressable onPress={onManageUsers} accessibilityRole="button" style={{ marginTop: 6 }}>
        <Text style={{ color: colors.accent, fontFamily: fonts.bodyMedium }}>Manage users</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { borderRadius: radii.lg, borderWidth: 1, padding: spacing.lg, gap: spacing.sm },
  title: { fontFamily: fonts.bodyMedium, fontSize: 16 },
});
