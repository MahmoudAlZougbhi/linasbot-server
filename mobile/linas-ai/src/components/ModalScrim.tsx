import type { ReactNode } from 'react';
import { Pressable, StyleSheet, type StyleProp, type ViewStyle } from 'react-native';

import { useTheme } from '../theme';

type Props = {
  onPress?: () => void;
  style?: StyleProp<ViewStyle>;
  children?: ReactNode;
  /** Bottom sheet default; center for dialogs. */
  justify?: 'flex-end' | 'center';
  accessibilityLabel?: string;
};

/** Semi-transparent dim overlay — never opaque black. Covers full screen incl. safe areas. */
export function ModalScrim({ onPress, style, children, justify = 'flex-end', accessibilityLabel }: Props) {
  const { colors } = useTheme();
  return (
    <Pressable
      style={[styles.base, { backgroundColor: colors.overlay, justifyContent: justify }, style]}
      onPress={onPress}
      accessibilityLabel={accessibilityLabel}
    >
      {children}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: StyleSheet.absoluteFill,
});
