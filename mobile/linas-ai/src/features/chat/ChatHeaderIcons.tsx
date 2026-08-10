import { StyleSheet, View } from 'react-native';

import { AppIcon } from '../../components/AppIcon';
import { NEW_CHAT_ICON } from '../nav/moduleIcons';

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
 * Used by chat header and drawer bottom New Chat — same artwork, optional size.
 */
export function NewChatIcon({ color, size = 22 }: { color: string; size?: number }) {
  return <AppIcon icon={NEW_CHAT_ICON} size={size} color={color} />;
}

const styles = StyleSheet.create({
  menu: {
    width: 22,
    height: 16,
    justifyContent: 'space-between',
  },
  menuBar: {
    height: 2,
    borderRadius: 1,
    width: '100%',
  },
});
