import type { ReactNode } from 'react';
import { StyleSheet, View, type ViewStyle } from 'react-native';

import { colors } from '../theme';

type Props = {
  children: ReactNode;
  style?: ViewStyle;
};

/** Soft light wash — calm depth without neon or black heaviness. */
export function GradientBackground({ children, style }: Props) {
  return (
    <View style={[styles.root, style]}>
      <View style={styles.topWash} pointerEvents="none" />
      <View style={styles.glow} pointerEvents="none" />
      <View style={styles.bottomWash} pointerEvents="none" />
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  topWash: {
    ...StyleSheet.absoluteFill,
    height: '38%',
    backgroundColor: colors.bgElevated,
    opacity: 0.9,
  },
  glow: {
    position: 'absolute',
    top: -100,
    right: -60,
    width: 260,
    height: 260,
    borderRadius: 130,
    backgroundColor: colors.accentGlow,
  },
  bottomWash: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    height: '22%',
    backgroundColor: colors.surfaceAlt,
    opacity: 0.55,
  },
});
