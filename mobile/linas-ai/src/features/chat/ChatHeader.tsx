import { StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useI18n } from '../../i18n/LanguageContext';
import { spacing, useTheme } from '../../theme';
import { HEADER_HIT, HeaderMenuButton } from './ChatHeaderIcons';
import { ChatTopFade } from './ChatTopFade';

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
      <HeaderMenuButton onPress={onOpenMenu} accessibilityLabel={tr('openMenu')} />
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
});
