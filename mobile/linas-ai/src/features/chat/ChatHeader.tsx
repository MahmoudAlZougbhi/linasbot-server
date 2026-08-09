import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { LinasStarMark } from '../../components/LinasStarMark';
import { useI18n } from '../../i18n/LanguageContext';
import { HIT, fonts, spacing, useTheme } from '../../theme';
import { MenuIcon } from './ChatHeaderIcons';

type Props = {
  isAuthenticated: boolean;
  workspaceLabel?: string | null;
  onOpenMenu: () => void;
  onSignIn?: () => void;
};

/** Header chrome: menu left, brand center, Sign in right for guests. New chat lives in NavDrawer. */
export function ChatHeader({
  isAuthenticated,
  workspaceLabel,
  onOpenMenu,
  onSignIn,
}: Props) {
  const insets = useSafeAreaInsets();
  const { colors } = useTheme();
  const { tr } = useI18n();
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
        accessibilityLabel={tr('openMenu')}
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
        <View
          style={styles.hit}
          accessibilityElementsHidden
          importantForAccessibility="no-hide-descendants"
        />
      ) : (
        <Pressable
          onPress={onSignIn}
          style={({ pressed }) => [styles.signIn, pressed && styles.pressed]}
          accessibilityLabel={tr('signIn')}
          accessibilityRole="button"
          hitSlop={8}
        >
          <Text style={{ color: colors.accent, fontFamily: fonts.bodyMedium, fontSize: 15 }}>
            {tr('signIn')}
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
