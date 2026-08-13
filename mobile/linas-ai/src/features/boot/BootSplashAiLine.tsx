import { useEffect, useRef } from 'react';
import { Animated, Easing, Platform, StyleSheet, View } from 'react-native';

import { bootSplashTokens as t } from './bootSplashTokens';

type Props = {
  reduceMotion?: boolean;
};

const GRADIENT_STOPS = [
  { flex: 0.35, color: t.lineGradientStart, opacity: 1 },
  { flex: 0.35, color: t.lineGradientMid, opacity: 0.85 },
  { flex: 0.3, color: t.lineGradientMid, opacity: 0 },
] as const;

function MovingSegment({ opacity }: { opacity: Animated.Value }) {
  return (
    <Animated.View
      pointerEvents="none"
      style={[
        styles.segmentWrap,
        {
          width: t.lineSegmentWidth,
          opacity,
          ...Platform.select({
            ios: {
              shadowColor: t.lineGlowColor,
              shadowOpacity: t.lineGlowOpacity,
              shadowRadius: t.lineGlowBlur,
              shadowOffset: { width: 0, height: 0 },
            },
            android: { elevation: 2 },
            default: {},
          }),
        },
      ]}
    >
      <View style={styles.segmentRow}>
        {GRADIENT_STOPS.map((stop, index) => (
          <View
            key={`grad-${index}`}
            style={{
              flex: stop.flex,
              height: t.lineHeight,
              backgroundColor: stop.color,
              opacity: stop.opacity,
              borderTopLeftRadius: index === 0 ? t.lineRadius : 0,
              borderBottomLeftRadius: index === 0 ? t.lineRadius : 0,
              borderTopRightRadius: index === GRADIENT_STOPS.length - 1 ? t.lineRadius : 0,
              borderBottomRightRadius: index === GRADIENT_STOPS.length - 1 ? t.lineRadius : 0,
            }}
          />
        ))}
      </View>
    </Animated.View>
  );
}

/** Teal AI loading line — L→R sweep with soft glow and opacity pulse. */
export function BootSplashAiLine({ reduceMotion = false }: Props) {
  const sweep = useRef(new Animated.Value(0)).current;
  const pulse = useRef(new Animated.Value(t.linePulseMin)).current;

  useEffect(() => {
    if (reduceMotion) {
      sweep.setValue(0.35);
      pulse.setValue(1);
      return;
    }

    const sweepLoop = Animated.loop(
      Animated.timing(sweep, {
        toValue: 1,
        duration: t.lineSweepMs,
        easing: Easing.linear,
        useNativeDriver: true,
      }),
    );

    const pulseLoop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, {
          toValue: t.linePulseMax,
          duration: t.linePulseMs / 2,
          easing: Easing.inOut(Easing.sin),
          useNativeDriver: true,
        }),
        Animated.timing(pulse, {
          toValue: t.linePulseMin,
          duration: t.linePulseMs / 2,
          easing: Easing.inOut(Easing.sin),
          useNativeDriver: true,
        }),
      ]),
    );

    sweepLoop.start();
    pulseLoop.start();
    return () => {
      sweepLoop.stop();
      pulseLoop.stop();
    };
  }, [pulse, reduceMotion, sweep]);

  const sweepX = sweep.interpolate({
    inputRange: [0, 1],
    outputRange: [-t.lineSegmentWidth, t.lineWidth],
  });

  return (
    <View style={styles.wrap}>
      <View style={styles.track} />
      {reduceMotion ? (
        <View style={styles.staticLight}>
          <MovingSegment opacity={pulse} />
        </View>
      ) : (
        <Animated.View style={[styles.moving, { transform: [{ translateX: sweepX }] }]}>
          <MovingSegment opacity={pulse} />
        </Animated.View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    width: t.lineWidth,
    height: t.lineHeight,
    overflow: 'hidden',
    borderRadius: t.lineRadius,
  },
  track: {
    ...StyleSheet.absoluteFill,
    backgroundColor: t.lineTrackColor,
    borderRadius: t.lineRadius,
  },
  moving: {
    position: 'absolute',
    top: 0,
    left: 0,
    height: t.lineHeight,
  },
  staticLight: {
    position: 'absolute',
    top: 0,
    left: (t.lineWidth - t.lineSegmentWidth) * 0.28,
    height: t.lineHeight,
  },
  segmentWrap: {
    height: t.lineHeight,
    borderRadius: t.lineRadius,
    overflow: 'hidden',
  },
  segmentRow: {
    flex: 1,
    flexDirection: 'row',
    height: t.lineHeight,
  },
});
