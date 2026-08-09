import type { ReactNode } from 'react';
import { StyleSheet, View, type ViewStyle } from 'react-native';

import { colors } from '../theme';

type Props = {
  children: ReactNode;
  style?: ViewStyle;
};

/** Soft lavender wash matching approved Linas brand board. */
export function GradientBackground({ children, style }: Props) {
  return (
    <View style={[styles.root, style]}>
      <View style={styles.topWash} pointerEvents="none" />
      <View style={styles.glow} pointerEvents="none" />
      <View style={styles.cyanGlow} pointerEvents="none" />
      <View style={styles.bottomWash} pointerEvents="none" />
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  topWash: {
    ...StyleSheet.absoluteFill,
    height: '40%',
    backgroundColor: colors.bgElevated,
    opacity: 0.92,
  },
  glow: {
    position: 'absolute',
    top: -110,
    right: -70,
    width: 280,
    height: 280,
    borderRadius: 140,
    backgroundColor: colors.accentGlow,
  },
  cyanGlow: {
    position: 'absolute',
    top: 80,
    left: -80,
    width: 200,
    height: 200,
    borderRadius: 100,
    backgroundColor: 'rgba(126, 200, 232, 0.18)',
  },
  bottomWash: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    height: '24%',
    backgroundColor: colors.surfaceAlt,
    opacity: 0.6,
  },
});
