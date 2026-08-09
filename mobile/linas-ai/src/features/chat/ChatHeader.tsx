import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { colors, fonts, spacing } from '../../theme';
import { LinasAvatar } from '../linas/LinasAvatar';
import type { LinasAvatarState } from '../linas/avatarAssets';

type Props = {
  title: string;
  online?: boolean;
  avatarState?: LinasAvatarState;
  onOpenHistory: () => void;
  onOpenControl: () => void;
};

export function ChatHeader({
  title,
  online = true,
  avatarState = 'idle',
  onOpenHistory,
  onOpenControl,
}: Props) {
  const insets = useSafeAreaInsets();
  return (
    <View style={[styles.bar, { paddingTop: insets.top + 8 }]}>
      <Pressable onPress={onOpenHistory} hitSlop={12} style={styles.hit} accessibilityLabel="Chat history">
        <Text style={styles.icon}>☰</Text>
      </Pressable>
      <View style={styles.center}>
        <LinasAvatar state={avatarState} size={36} active />
        <View style={styles.copy}>
          <Text style={styles.brand}>Linas AI</Text>
          <View style={styles.statusRow}>
            <View style={[styles.dot, !online && styles.dotOff]} />
            <Text style={styles.status} numberOfLines={1}>
              {online ? 'Online' : title}
            </Text>
          </View>
        </View>
      </View>
      <Pressable
        onPress={onOpenControl}
        hitSlop={12}
        style={styles.hit}
        accessibilityLabel="Control Center"
      >
        <Text style={styles.icon}>◈</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  bar: {
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.md,
    flexDirection: 'row',
    alignItems: 'center',
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSoft,
    backgroundColor: colors.bgElevated,
  },
  hit: {
    width: 40,
    height: 40,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 12,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
  },
  icon: { color: colors.accent, fontSize: 16, fontWeight: '700' },
  center: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
    paddingHorizontal: 8,
  },
  copy: { alignItems: 'flex-start', maxWidth: '70%' },
  brand: { color: colors.accentDeep, fontFamily: fonts.bodyMedium, fontSize: 15 },
  statusRow: { flexDirection: 'row', alignItems: 'center', gap: 5, marginTop: 2 },
  dot: { width: 7, height: 7, borderRadius: 4, backgroundColor: colors.success },
  dotOff: { backgroundColor: colors.textDim },
  status: { color: colors.textMuted, fontFamily: fonts.body, fontSize: 11, maxWidth: 160 },
});
