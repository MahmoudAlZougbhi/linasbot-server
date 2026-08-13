import { StyleSheet, View, type ViewStyle } from 'react-native';

import { LinasSparkleIcon } from './LinasSparkleIcon';
import { useTheme } from '../theme';

type Props = {
  size?: number;
  color?: string;
  dotColor?: string;
  style?: ViewStyle;
};

/**
 * Canonical Linas brand mark: four-point sparkle + signal dot.
 * Dot placement matches assets/linas-app-icon.svg proportions.
 */
export function LinasSparkleMark({ size = 56, color, dotColor, style }: Props) {
  const { colors } = useTheme();
  const markColor = color ?? colors.accent;
  const signalColor = dotColor ?? colors.accentMid;
  const dotSize = Math.max(6, Math.round(size * 0.14));
  const dotOffsetX = size * 0.37;
  const dotOffsetY = size * 0.37;

  return (
    <View style={[styles.wrap, { width: size + dotOffsetX, height: size + dotOffsetY }, style]}>
      <LinasSparkleIcon size={size} color={markColor} />
      <View
        style={[
          styles.dot,
          {
            width: dotSize,
            height: dotSize,
            borderRadius: dotSize / 2,
            backgroundColor: signalColor,
            left: size - dotSize * 0.35,
            top: size - dotSize * 0.2,
          },
        ]}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    alignItems: 'flex-start',
    justifyContent: 'flex-start',
  },
  dot: {
    position: 'absolute',
  },
});
