import type { ReactNode } from 'react';
import { StyleSheet, View, type ViewStyle } from 'react-native';

import { useTheme } from '../theme';

type Props = {
  children: ReactNode;
  style?: ViewStyle;
};

/**
 * Soft top wash matching PDF handoff light/dark tokens.
 * No bottom wash / elevation strip — that read as a green shadowed bar above the chat composer.
 */
export function GradientBackground({ children, style }: Props) {
  const { colors } = useTheme();
  return (
    <View style={[styles.root, { backgroundColor: colors.bg }, style]}>
      <View
        style={[styles.topWash, { backgroundColor: colors.bgElevated }]}
        pointerEvents="none"
      />
      <View style={[styles.glow, { backgroundColor: colors.accentGlow }]} pointerEvents="none" />
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
});
