import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { LinasStarMark } from '../../components/LinasStarMark';
import { HIT, fonts, spacing, useTheme } from '../../theme';

type Props = {
  isAuthenticated: boolean;
  workspaceLabel?: string | null;
  onOpenMenu: () => void;
  onSignIn?: () => void;
  onNewChat?: () => void;
};

export function ChatHeader({
  isAuthenticated,
  workspaceLabel,
  onOpenMenu,
  onSignIn,
  onNewChat,
}: Props) {
  const insets = useSafeAreaInsets();
  const { colors } = useTheme();

  return (
    <View
      style={[
        styles.bar,
        {
          paddingTop: insets.top + 8,
          borderBottomColor: colors.borderSoft,
          backgroundColor: colors.bgElevated,
        },
      ]}
    >
      <Pressable
        onPress={onOpenMenu}
        style={[styles.hit, { borderColor: colors.border, backgroundColor: colors.surface }]}
        accessibilityLabel="Open menu"
        accessibilityRole="button"
      >
        <Text style={{ color: colors.accent, fontSize: 18, fontWeight: '700' }}>☰</Text>
      </Pressable>

      <View style={styles.center}>
        <LinasStarMark labeled size={18} />
        {isAuthenticated && workspaceLabel ? (
          <Text style={[styles.workspace, { color: colors.textMuted }]} numberOfLines={1}>
            {workspaceLabel}
          </Text>
        ) : null}
      </View>

      {isAuthenticated ? (
        <Pressable
          onPress={onNewChat}
          style={[styles.hit, { borderColor: colors.border, backgroundColor: colors.surface }]}
          accessibilityLabel="New chat"
          accessibilityRole="button"
        >
          <Text style={{ color: colors.accent, fontSize: 16 }}>✎</Text>
        </Pressable>
      ) : (
        <Pressable
          onPress={onSignIn}
          style={styles.signIn}
          accessibilityLabel="Sign in"
          accessibilityRole="button"
          hitSlop={8}
        >
          <Text style={{ color: colors.accent, fontFamily: fonts.bodyMedium, fontSize: 15 }}>
            Sign in
          </Text>
        </Pressable>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  bar: {
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.md,
    flexDirection: 'row',
    alignItems: 'center',
  },
  hit: {
    width: HIT,
    height: HIT,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 14,
    borderWidth: 1,
  },
  center: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 8,
    gap: 2,
  },
  workspace: {
    fontFamily: fonts.body,
    fontSize: 11,
    maxWidth: 180,
  },
  signIn: {
    minWidth: HIT,
    minHeight: HIT,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 8,
  },
});
