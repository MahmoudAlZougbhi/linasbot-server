import { StyleSheet, View } from 'react-native';

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
 * ChatGPT-style “new chat” compose mark: rounded square + pencil.
 * Drawn with Views so we stay dependency-free (no vector-icons / svg).
 */
export function NewChatIcon({ color }: { color: string }) {
  return (
    <View accessible={false} style={styles.compose}>
      <View style={[styles.composePad, { borderColor: color }]} />
      <View style={[styles.composePenBody, { backgroundColor: color }]} />
      <View style={[styles.composePenTip, { borderTopColor: color }]} />
    </View>
  );
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
  compose: {
    width: 22,
    height: 22,
  },
  composePad: {
    position: 'absolute',
    left: 0,
    bottom: 0,
    width: 15,
    height: 15,
    borderWidth: 1.85,
    borderRadius: 3.5,
  },
  composePenBody: {
    position: 'absolute',
    width: 11,
    height: 1.85,
    borderRadius: 1,
    right: 0.5,
    top: 5.5,
    transform: [{ rotate: '-45deg' }],
  },
  composePenTip: {
    position: 'absolute',
    right: 1,
    top: 1,
    width: 0,
    height: 0,
    borderLeftWidth: 3.2,
    borderRightWidth: 3.2,
    borderTopWidth: 4.2,
    borderLeftColor: 'transparent',
    borderRightColor: 'transparent',
    transform: [{ rotate: '45deg' }],
  },
});
