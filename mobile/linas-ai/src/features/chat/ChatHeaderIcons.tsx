import type { ReactNode } from 'react';
import { StyleSheet, View } from 'react-native';

import { AppIcon } from '../../components/AppIcon';
import { radii } from '../../theme';
import { NEW_CHAT_ICON } from '../nav/moduleIcons';

/** Light-gray rounded square behind the overlay hamburger. */
export const HEADER_ICON_BOX = 36;

export function HeaderIconBox({
  children,
  backgroundColor,
  borderColor,
}: {
  children: ReactNode;
  backgroundColor: string;
  borderColor: string;
}) {
  return (
    <View style={[styles.box, { backgroundColor, borderColor }]}>
      {children}
    </View>
  );
}

/** Clean 3-bar hamburger matching PDF / ChatGPT header (no emoji). */
export function MenuIcon({ color }: { color: string }) {
  return (
    <View accessible={false} style={styles.menu}>
      <View style={[styles.menuBar, { backgroundColor: color }]} />
      <View style={[styles.menuBar, { backgroundColor: color }]} />
      <View style={[styles.menuBar, { backgroundColor: color }]} />
    </View>
  );
}

/**
 * Shared ChatGPT-style “new chat” compose mark (square + pencil).
 * Used by the drawer New Chat control — same artwork, optional size.
 */
export function NewChatIcon({ color, size = 20 }: { color: string; size?: number }) {
  return <AppIcon icon={NEW_CHAT_ICON} size={size} color={color} />;
}

const styles = StyleSheet.create({
  box: {
    width: HEADER_ICON_BOX,
    height: HEADER_ICON_BOX,
    borderRadius: radii.sm,
    borderWidth: StyleSheet.hairlineWidth,
    alignItems: 'center',
    justifyContent: 'center',
  },
  menu: {
    width: 18,
    height: 13,
    justifyContent: 'space-between',
  },
  menuBar: {
    height: 1.75,
    borderRadius: 1,
    width: '100%',
  },
});
