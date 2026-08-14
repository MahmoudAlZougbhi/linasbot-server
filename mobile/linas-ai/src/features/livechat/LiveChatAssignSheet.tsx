import { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { tokenStore } from '../../auth/tokenStore';
import { PrimaryButton } from '../../components/PrimaryButton';
import { fonts, radii, spacing, useTheme } from '../../theme';
import { classifyUsersError, listUsers, type TeamUser } from '../users/usersApi';
import { assigneeFirstName } from './liveChatTypes';

export type StaffPick = { id: string; label: string };

type Props = {
  visible: boolean;
  busy: boolean;
  onClose: () => void;
  onPick: (staff: StaffPick) => void;
};

function labelFor(user: { id: string; name?: string | null; displayName?: string | null; email?: string | null }): string {
  return (
    assigneeFirstName(user.name || user.displayName || user.email) ||
    user.email ||
    user.id
  );
}

export function LiveChatAssignSheet({ visible, busy, onClose, onPick }: Props) {
  const { colors } = useTheme();
  const [staff, setStaff] = useState<StaffPick[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [listRestricted, setListRestricted] = useState(false);

  useEffect(() => {
    if (!visible) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setListRestricted(false);
    void (async () => {
      try {
        const users: TeamUser[] = await listUsers();
        const active = users.filter((u) => String(u.status || 'active').toLowerCase() !== 'inactive');
        if (!cancelled) {
          setStaff(active.map((u) => ({ id: u.id, label: labelFor(u) })));
        }
      } catch (err) {
        const kind = classifyUsersError(err);
        const me = await tokenStore.getUser();
        if (cancelled) return;
        if (me) {
          setStaff([{ id: me.id, label: labelFor(me) }]);
        } else {
          setStaff([]);
        }
        if (kind === 'forbidden') {
          setListRestricted(true);
        } else {
          setError(err instanceof Error ? err.message : 'Could not load staff.');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [visible]);

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <View style={[styles.backdrop, { backgroundColor: colors.overlay }]}>
        <View style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}>
          <Text style={[styles.title, { color: colors.text }]}>Assign to staff</Text>
          {listRestricted ? (
            <Text style={[styles.hint, { color: colors.textMuted }]}>
              Your account can assign this chat to yourself. Listing other employees needs Users
              permission.
            </Text>
          ) : (
            <Text style={[styles.hint, { color: colors.textMuted }]}>
              Choose a workspace member. This takes the conversation from AI.
            </Text>
          )}
          {loading ? <ActivityIndicator color={colors.accent} /> : null}
          {error ? <Text style={[styles.error, { color: colors.danger }]}>{error}</Text> : null}
          <ScrollView style={styles.list}>
            {staff.map((person) => (
              <Pressable
                key={person.id}
                onPress={() => onPick(person)}
                disabled={busy}
                style={[styles.row, { borderBottomColor: colors.borderSoft }]}
                accessibilityRole="button"
                accessibilityLabel={`Assign to ${person.label}`}
              >
                <Text style={[styles.name, { color: colors.text }]}>{person.label}</Text>
              </Pressable>
            ))}
          </ScrollView>
          <PrimaryButton label="Cancel" onPress={onClose} variant="ghost" disabled={busy} />
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, justifyContent: 'center', padding: spacing.xl },
  card: { borderWidth: 1, borderRadius: radii.lg, padding: spacing.xl, maxHeight: '70%' },
  title: { fontFamily: fonts.bodyMedium, fontSize: 18, marginBottom: spacing.sm },
  hint: { fontFamily: fonts.body, fontSize: 13, marginBottom: spacing.md },
  error: { fontFamily: fonts.body, fontSize: 13, marginBottom: spacing.sm },
  list: { maxHeight: 280, marginBottom: spacing.md },
  row: { paddingVertical: 12, borderBottomWidth: StyleSheet.hairlineWidth },
  name: { fontFamily: fonts.bodyMedium, fontSize: 16 },
});
