import { Pressable, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useI18n } from '../../i18n/LanguageContext';
import { spacing, useTheme } from '../../theme';
import { HeaderIconBox, MenuIcon } from './ChatHeaderIcons';
import { ChatTopFade } from './ChatTopFade';

/** Compact 44pt hit around the 36pt silver menu square. */
const HEADER_HIT = 44;
/** Extra space below status bar / notch (on top of safe-area inset). */
const HEADER_TOP_GAP = 2;
/** Gap under the hamburger / fade so the first bubble is not cramped into them. */
const LIST_BELOW_OVERLAY_GAP = spacing.md + spacing.sm;
/** List padding so the first message sits just below the overlay, not in the notch. */
export const CHAT_LIST_TOP_CLEARANCE = HEADER_HIT + HEADER_TOP_GAP + LIST_BELOW_OVERLAY_GAP;

type Props = {
  onOpenMenu: () => void;
};

/** Overlay hamburger + light top fade — no title, sparkle, or new-chat. */
export function ChatHeader({ onOpenMenu }: Props) {
  const insets = useSafeAreaInsets();
  const { colors } = useTheme();
  const { tr } = useI18n();

  return (
    <View
      pointerEvents="box-none"
      style={[styles.overlay, { paddingTop: insets.top + HEADER_TOP_GAP }]}
    >
      <ChatTopFade insetTop={insets.top} color={colors.bg} />
      <Pressable
        onPress={onOpenMenu}
        style={({ pressed }) => [styles.hit, pressed && styles.pressed]}
        accessibilityLabel={tr('openMenu')}
        accessibilityRole="button"
        hitSlop={4}
      >
        <HeaderIconBox backgroundColor={colors.featuredIconBg} borderColor={colors.featuredIconBorder}>
          <MenuIcon color={colors.text} />
        </HeaderIconBox>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  overlay: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    zIndex: 20,
    paddingHorizontal: spacing.md,
    direction: 'ltr',
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
});
