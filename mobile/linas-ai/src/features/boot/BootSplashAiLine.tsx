import { useEffect, useRef } from 'react';
import { Animated, Easing, StyleSheet, View } from 'react-native';

import { useTheme } from '../../theme';

const LINE_WIDTH = 132;
const LINE_HEIGHT = 2;
const SEGMENTS = 14;
const SHIMMER_WIDTH = 36;

type Props = {
  reduceMotion?: boolean;
};

/** Teal fade line with a soft AI shimmer sweep — native-driver only. */
export function BootSplashAiLine({ reduceMotion = false }: Props) {
  const { colors } = useTheme();
  const sweep = useRef(new Animated.Value(0)).current;
  const breathe = useRef(new Animated.Value(0.88)).current;

  useEffect(() => {
    if (reduceMotion) {
      sweep.setValue(0);
      breathe.setValue(1);
      return;
    }

    const sweepLoop = Animated.loop(
      Animated.sequence([
        Animated.timing(sweep, {
          toValue: 1,
          duration: 2200,
          easing: Easing.inOut(Easing.cubic),
          useNativeDriver: true,
        }),
        Animated.delay(320),
      ]),
    );

    const breatheLoop = Animated.loop(
      Animated.sequence([
        Animated.timing(breathe, {
          toValue: 1,
          duration: 1400,
          easing: Easing.inOut(Easing.sin),
          useNativeDriver: true,
        }),
        Animated.timing(breathe, {
          toValue: 0.82,
          duration: 1400,
          easing: Easing.inOut(Easing.sin),
          useNativeDriver: true,
        }),
      ]),
    );

    sweepLoop.start();
    breatheLoop.start();
    return () => {
      sweepLoop.stop();
      breatheLoop.stop();
    };
  }, [breathe, reduceMotion, sweep]);

  const shimmerX = sweep.interpolate({
    inputRange: [0, 1],
    outputRange: [-SHIMMER_WIDTH, LINE_WIDTH],
  });

  const fadeSteps = Array.from({ length: SEGMENTS }, (_, index) =>
    SEGMENTS <= 1 ? 1 : 1 - index / (SEGMENTS - 1),
  );

  return (
    <Animated.View style={[styles.wrap, { opacity: breathe }]}>
      <View style={styles.track}>
        {fadeSteps.map((opacity, index) => (
          <View
            key={`seg-${index}`}
            style={[styles.segment, { backgroundColor: colors.accent, opacity }]}
          />
        ))}
      </View>
      {reduceMotion ? null : (
        <Animated.View
          pointerEvents="none"
          style={[
            styles.shimmer,
            {
              width: SHIMMER_WIDTH,
              backgroundColor: colors.accentMid,
              transform: [{ translateX: shimmerX }],
            },
          ]}
        />
      )}
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    width: LINE_WIDTH,
    height: LINE_HEIGHT,
    marginTop: 14,
    overflow: 'hidden',
    borderRadius: LINE_HEIGHT,
  },
  track: {
    position: 'absolute',
    left: 0,
    right: 0,
    top: 0,
    bottom: 0,
    flexDirection: 'row',
    alignItems: 'center',
  },
  segment: {
    flex: 1,
    height: LINE_HEIGHT,
  },
  shimmer: {
    position: 'absolute',
    top: 0,
    bottom: 0,
    opacity: 0.55,
    borderRadius: LINE_HEIGHT,
  },
});
