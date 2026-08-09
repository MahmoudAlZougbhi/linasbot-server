import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { LinasStarMark } from '../../components/LinasStarMark';
import { HIT, fonts, spacing, useTheme } from '../../theme';
import { MenuIcon, NewChatIcon } from './ChatHeaderIcons';

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
  const iconColor = colors.text;

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
        style={({ pressed }) => [styles.hit, pressed && styles.pressed]}
        accessibilityLabel="Open menu"
        accessibilityRole="button"
        hitSlop={4}
      >
        <MenuIcon color={iconColor} />
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
          style={({ pressed }) => [styles.hit, pressed && styles.pressed]}
          accessibilityLabel="New chat"
          accessibilityRole="button"
          hitSlop={4}
        >
          <NewChatIcon color={iconColor} />
        </Pressable>
      ) : (
        <Pressable
          onPress={onSignIn}
          style={({ pressed }) => [styles.signIn, pressed && styles.pressed]}
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
    paddingHorizontal: spacing.md,
    paddingBottom: spacing.md,
    flexDirection: 'row',
    alignItems: 'center',
  },
  hit: {
    width: HIT,
    height: HIT,
    alignItems: 'center',
    justifyContent: 'center',
  },
  pressed: {
    opacity: 0.55,
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
