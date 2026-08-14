import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { LinasStarMark } from '../../components/LinasStarMark';
import { useI18n } from '../../i18n/LanguageContext';
import { fonts, spacing, useTheme } from '../../theme';
import { HeaderIconBox, MenuIcon, NewChatIcon } from './ChatHeaderIcons';

/** Compact header row; 44pt meets Apple HIG while shrinking chrome. */
const HEADER_HIT = 44;
/** Extra space below status bar / notch (on top of safe-area inset). */
const HEADER_TOP_GAP = 2;

type Props = {
  isAuthenticated: boolean;
  workspaceLabel?: string | null;
  onOpenMenu: () => void;
  onNewChat?: () => void;
  onSignIn?: () => void;
};

/** Header: menu square | ✦ Linas AI | new-chat square (auth) or Sign in (guest). */
export function ChatHeader({
  isAuthenticated,
  onOpenMenu,
  onNewChat,
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
          paddingTop: insets.top + HEADER_TOP_GAP,
          backgroundColor: colors.bg,
          borderBottomColor: colors.borderSoft,
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
        <HeaderIconBox backgroundColor={colors.featuredIconBg} borderColor={colors.featuredIconBorder}>
          <MenuIcon color={iconColor} />
        </HeaderIconBox>
      </Pressable>

      <View style={styles.center}>
        <LinasStarMark
          labeled
          size={16}
          label="Linas AI"
          labelColor={colors.accentDeep}
        />
      </View>

      {isAuthenticated && onNewChat ? (
        <Pressable
          onPress={onNewChat}
          style={({ pressed }) => [styles.hit, pressed && styles.pressed]}
          accessibilityLabel={tr('newChat')}
          accessibilityRole="button"
          hitSlop={4}
        >
          <HeaderIconBox backgroundColor={colors.featuredIconBg} borderColor={colors.featuredIconBorder}>
            <NewChatIcon color={iconColor} size={18} />
          </HeaderIconBox>
        </Pressable>
      ) : !isAuthenticated ? (
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
      ) : (
        <View
          style={styles.hit}
          accessibilityElementsHidden
          importantForAccessibility="no-hide-descendants"
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  bar: {
    paddingHorizontal: spacing.md,
    paddingBottom: spacing.sm,
    flexDirection: 'row',
    alignItems: 'center',
    direction: 'ltr',
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  hit: {
    width: HEADER_HIT,
    height: HEADER_HIT,
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
  },
  signIn: {
    minWidth: HEADER_HIT,
    minHeight: HEADER_HIT,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 8,
  },
});
