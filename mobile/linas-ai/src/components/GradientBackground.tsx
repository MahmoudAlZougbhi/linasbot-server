import type { ReactNode } from 'react';
import { StyleSheet, View, type ViewStyle } from 'react-native';

import { colors } from '../theme';

type Props = {
  children: ReactNode;
  style?: ViewStyle;
};

/** Soft layered wash — calm depth without neon or extra native deps. */
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
    height: '42%',
    backgroundColor: colors.bgElevated,
    opacity: 0.85,
  },
  glow: {
    position: 'absolute',
    top: -90,
    right: -50,
    width: 240,
    height: 240,
    borderRadius: 120,
    backgroundColor: colors.accentGlow,
  },
  bottomWash: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    height: '28%',
    backgroundColor: '#0A101C',
    opacity: 0.7,
  },
});
