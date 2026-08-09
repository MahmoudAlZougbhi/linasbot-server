import type { ReactNode } from 'react';
import { StyleSheet, View, type ViewStyle } from 'react-native';

import { useTheme } from '../theme';

type Props = {
  children: ReactNode;
  style?: ViewStyle;
};

/** Soft teal wash matching PDF handoff light/dark tokens. */
export function GradientBackground({ children, style }: Props) {
  const { colors } = useTheme();
  return (
    <View style={[styles.root, { backgroundColor: colors.bg }, style]}>
      <View
        style={[styles.topWash, { backgroundColor: colors.bgElevated }]}
        pointerEvents="none"
      />
      <View style={[styles.glow, { backgroundColor: colors.accentGlow }]} pointerEvents="none" />
      <View
        style={[styles.bottomWash, { backgroundColor: colors.surfaceAlt }]}
        pointerEvents="none"
      />
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  topWash: {
    ...StyleSheet.absoluteFill,
    height: '40%',
    opacity: 0.92,
  },
  glow: {
    position: 'absolute',
    top: -110,
    right: -70,
    width: 280,
    height: 280,
    borderRadius: 140,
  },
  bottomWash: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    height: '24%',
    opacity: 0.55,
  },
});
