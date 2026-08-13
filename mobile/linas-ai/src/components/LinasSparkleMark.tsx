import { StyleSheet, View, type ViewStyle } from 'react-native';

import { LinasSparkleIcon } from './LinasSparkleIcon';
import { useTheme } from '../theme';

type Props = {
  size?: number;
  color?: string;
  dotColor?: string;
  /** Override signal dot diameter (pt). */
  dotSize?: number;
  /** Gap between sparkle edge and dot center (pt), lower-right. */
  dotGap?: number;
  style?: ViewStyle;
};

/**
 * Canonical Linas brand mark: four-point sparkle + signal dot.
 * Dot placement matches assets/linas-app-icon.svg proportions.
 */
export function LinasSparkleMark({
  size = 56,
  color,
  dotColor,
  dotSize: dotSizeProp,
  dotGap,
  style,
}: Props) {
  const { colors } = useTheme();
  const markColor = color ?? colors.accent;
  const signalColor = dotColor ?? colors.accentMid;
  const dotSize = dotSizeProp ?? Math.max(6, Math.round(size * 0.14));

  let dotLeft: number;
  let dotTop: number;
  let wrapWidth: number;
  let wrapHeight: number;

  if (dotGap != null) {
    dotLeft = size + dotGap - dotSize / 2;
    dotTop = size + dotGap - dotSize / 2;
    wrapWidth = Math.max(size, dotLeft + dotSize);
    wrapHeight = wrapWidth;
  } else {
    const dotOffsetX = size * 0.37;
    const dotOffsetY = size * 0.37;
    dotLeft = size - dotSize * 0.35;
    dotTop = size - dotSize * 0.2;
    wrapWidth = size + dotOffsetX;
    wrapHeight = size + dotOffsetY;
  }

  return (
    <View style={[styles.wrap, { width: wrapWidth, height: wrapHeight }, style]}>
      <LinasSparkleIcon size={size} color={markColor} />
      <View
        style={[
          styles.dot,
          {
            width: dotSize,
            height: dotSize,
            borderRadius: dotSize / 2,
            backgroundColor: signalColor,
            left: dotLeft,
            top: dotTop,
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
