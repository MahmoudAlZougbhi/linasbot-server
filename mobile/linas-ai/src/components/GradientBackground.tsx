import type { ReactNode } from 'react';
import { StyleSheet, View, type ViewStyle } from 'react-native';

import { useTheme } from '../theme';

type Props = {
  children: ReactNode;
  style?: ViewStyle;
};

/** Flat chat canvas — matches PDF handoff light/dark tokens. */
export function GradientBackground({ children, style }: Props) {
  const { colors } = useTheme();
  return (
    <View style={[styles.root, { backgroundColor: colors.bg }, style]}>
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
});
