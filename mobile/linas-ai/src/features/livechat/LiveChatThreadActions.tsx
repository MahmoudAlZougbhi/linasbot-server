import { Pressable, StyleSheet, Text, View } from 'react-native';

import { StatusChip } from '../../components/StatusChip';
import { fonts, radii, spacing, useTheme } from '../../theme';
import { type LiveChatItem, normalizeStatus, statusLabel, statusTone } from './liveChatTypes';

type Props = {
  chat: LiveChatItem;
  localStatus: string;
  busy: boolean;
  onTakeover: () => void;
  onRelease: () => void;
  onAssign: () => void;
};

export function LiveChatThreadActions({
  chat,
  localStatus,
  busy,
  onTakeover,
  onRelease,
  onAssign,
}: Props) {
  const { colors } = useTheme();
  const status = normalizeStatus({ ...chat, status: localStatus });
  const human = status === 'human' || status === 'waiting_human';

  return (
    <View style={[styles.bar, { borderBottomColor: colors.border }]}>
      <StatusChip label={statusLabel(status)} tone={statusTone(status)} />
      <View style={styles.actions}>
        {!human ? (
            <Pressable
              onPress={onTakeover}
              disabled={busy}
              style={[styles.btn, { backgroundColor: colors.accent }]}
              accessibilityRole="button"
              accessibilityLabel="Take over from AI"
            >
              <Text style={[styles.primary, { color: colors.onAccent }]}>Take over</Text>
            </Pressable>
          ) : (
            <Pressable
              onPress={onRelease}
              disabled={busy}
              style={[styles.btn, { borderColor: colors.border, backgroundColor: colors.surface }]}
              accessibilityRole="button"
              accessibilityLabel="Resume AI"
            >
              <Text style={[styles.ghost, { color: colors.text }]}>Resume AI</Text>
            </Pressable>
          )}
          <Pressable
            onPress={onAssign}
            disabled={busy}
            style={[styles.btn, { borderColor: colors.border, backgroundColor: colors.surface }]}
            accessibilityRole="button"
            accessibilityLabel="Assign to staff"
          >
            <Text style={[styles.ghost, { color: colors.text }]}>Assign</Text>
          </Pressable>
        </View>
    </View>
  );
}

const styles = StyleSheet.create({
  bar: {
    flexDirection: 'row',
    alignItems: 'center',
    flexWrap: 'wrap',
    gap: 8,
    marginBottom: spacing.sm,
    paddingBottom: spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  actions: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, flex: 1, justifyContent: 'flex-end' },
  btn: {
    borderRadius: radii.md,
    paddingVertical: 8,
    paddingHorizontal: 12,
    borderWidth: 1,
    borderColor: 'transparent',
  },
  primary: { fontFamily: fonts.bodyMedium, fontSize: 13 },
  ghost: { fontFamily: fonts.bodyMedium, fontSize: 13 },
});
