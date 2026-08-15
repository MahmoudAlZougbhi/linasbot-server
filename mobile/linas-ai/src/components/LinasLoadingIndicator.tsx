import { useEffect, useRef } from 'react';
import { Animated, Easing, StyleSheet, View, type ViewStyle } from 'react-native';

import { useReduceMotion } from '../hooks/useReduceMotion';
import { LinasStarMark } from './LinasStarMark';

type Variant = 'screen' | 'inline';

type Props = {
  /** Full-screen centered vs compact inline mark. */
  variant?: Variant;
  /** Sparkle size for inline variant (screen uses 44). */
  size?: number;
  style?: ViewStyle;
};

const SCREEN_MARK_SIZE = 44;
const INLINE_MARK_SIZE = 32;

/**
 * Branded Linas sparkle loader — gentle breathe/pulse, no gray ActivityIndicator.
 * Use `screen` for initial page loads; `inline` for list footers and compact slots.
 */
export function LinasLoadingIndicator({
  variant = 'inline',
  size = INLINE_MARK_SIZE,
  style,
}: Props) {
  const reduceMotion = useReduceMotion();
  const scale = useRef(new Animated.Value(1)).current;
  const markSize = variant === 'screen' ? SCREEN_MARK_SIZE : size;

  useEffect(() => {
    scale.stopAnimation();
    if (reduceMotion) {
      scale.setValue(1);
      return;
    }
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(scale, {
          toValue: 1.1,
          duration: 900,
          easing: Easing.inOut(Easing.sin),
          useNativeDriver: true,
        }),
        Animated.timing(scale, {
          toValue: 0.92,
          duration: 900,
          easing: Easing.inOut(Easing.sin),
          useNativeDriver: true,
        }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [reduceMotion, scale]);

  const mark = (
    <Animated.View
      style={{ transform: [{ scale }] }}
      accessibilityRole="progressbar"
      accessibilityLabel="Loading"
    >
      <LinasStarMark size={markSize} />
    </Animated.View>
  );

  if (variant === 'screen') {
    return <View style={[styles.screen, style]}>{mark}</View>;
  }

  return <View style={[styles.inline, style]}>{mark}</View>;
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    minHeight: 240,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 48,
  },
  inline: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 12,
  },
});
