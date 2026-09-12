import { useEffect, useRef } from 'react';
import { Animated, Easing, StyleSheet, View } from 'react-native';

import { useReduceMotion } from '../../hooks/useReduceMotion';

/** Landing `.lp-typing` / `@keyframes lp-dots` in dashboard/src/styles/landing.css. */
export const TYPING_DOT_CYCLE_MS = 1000;
export const TYPING_DOT_STAGGER_MS = 150;
export const TYPING_DOT_SIZE = 6;
/** Landing `.lp-typing span` fill. */
export const TYPING_DOT_COLOR = '#06715F';
const DOT_COUNT = 3;

type Props = {
  color: string;
};

/**
 * Three-dot bounce used on the public Here phone chat while Linas is typing.
 */
export function TypingDots({ color }: Props) {
  const reduceMotion = useReduceMotion();
  const progress = useRef(
    Array.from({ length: DOT_COUNT }, () => new Animated.Value(0)),
  ).current;

  useEffect(() => {
    progress.forEach((value) => value.stopAnimation());
    if (reduceMotion) {
      progress.forEach((value) => value.setValue(0.4));
      return;
    }
    const loops = progress.map((value, index) => {
      value.setValue(0);
      const loop = Animated.loop(
        Animated.timing(value, {
          toValue: 1,
          duration: TYPING_DOT_CYCLE_MS,
          easing: Easing.linear,
          useNativeDriver: true,
        }),
      );
      const run = Animated.sequence([
        Animated.delay(index * TYPING_DOT_STAGGER_MS),
        loop,
      ]);
      run.start();
      return run;
    });
    return () => loops.forEach((run) => run.stop());
  }, [progress, reduceMotion]);

  return (
    <View style={styles.row} accessibilityElementsHidden importantForAccessibility="no-hide-descendants">
      {progress.map((value, index) => (
        <Animated.View
          key={index}
          style={[
            styles.dot,
            {
              backgroundColor: color,
              opacity: value.interpolate({
                inputRange: [0, 0.4, 0.8, 1],
                outputRange: [0.25, 1, 0.25, 0.25],
              }),
              transform: [
                {
                  translateY: value.interpolate({
                    inputRange: [0, 0.4, 0.8, 1],
                    outputRange: [0, -2, 0, 0],
                  }),
                },
              ],
            },
          ]}
        />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  dot: {
    width: TYPING_DOT_SIZE,
    height: TYPING_DOT_SIZE,
    marginHorizontal: 2,
    borderRadius: TYPING_DOT_SIZE,
  },
});
