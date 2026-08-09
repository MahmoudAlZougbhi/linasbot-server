import { useEffect, useRef, useState } from 'react';
import {
  AccessibilityInfo,
  Animated,
  Easing,
  Image,
  StyleSheet,
  View,
  type ImageStyle,
  type ViewStyle,
} from 'react-native';

import { colors } from '../../theme';
import { avatarSourceForState, type LinasAvatarState } from './avatarAssets';

type Props = {
  state?: LinasAvatarState;
  size?: number;
  circular?: boolean;
  style?: ViewStyle;
  /** Pause loops when off-screen / drawer closed. */
  active?: boolean;
};

export function LinasAvatar({
  state = 'idle',
  size = 48,
  circular = true,
  style,
  active = true,
}: Props) {
  const scale = useRef(new Animated.Value(1)).current;
  const glow = useRef(new Animated.Value(0.35)).current;
  const [reduceMotion, setReduceMotion] = useState(false);

  useEffect(() => {
    let mounted = true;
    void AccessibilityInfo.isReduceMotionEnabled().then((v) => {
      if (mounted) setReduceMotion(v);
    });
    const sub = AccessibilityInfo.addEventListener('reduceMotionChanged', setReduceMotion);
    return () => {
      mounted = false;
      sub.remove();
    };
  }, []);

  useEffect(() => {
    scale.stopAnimation();
    glow.stopAnimation();
    if (!active || reduceMotion) {
      scale.setValue(1);
      glow.setValue(0.25);
      return;
    }

    const calmLoop = (to: number, duration: number) =>
      Animated.loop(
        Animated.sequence([
          Animated.timing(scale, {
            toValue: to,
            duration,
            easing: Easing.inOut(Easing.sin),
            useNativeDriver: true,
          }),
          Animated.timing(scale, {
            toValue: 1,
            duration,
            easing: Easing.inOut(Easing.sin),
            useNativeDriver: true,
          }),
        ]),
      );

    const glowLoop = Animated.loop(
      Animated.sequence([
        Animated.timing(glow, {
          toValue: 0.7,
          duration: 1400,
          useNativeDriver: true,
        }),
        Animated.timing(glow, {
          toValue: 0.25,
          duration: 1400,
          useNativeDriver: true,
        }),
      ]),
    );

    let anim: Animated.CompositeAnimation | null = null;
    if (state === 'thinking' || state === 'typing') {
      anim = Animated.parallel([calmLoop(1.04, 700), glowLoop]);
    } else if (state === 'listening') {
      anim = Animated.parallel([calmLoop(1.06, 520), glowLoop]);
    } else if (state === 'welcome' || state === 'success' || state === 'excited') {
      anim = Animated.sequence([
        Animated.spring(scale, { toValue: 1.08, friction: 5, useNativeDriver: true }),
        Animated.spring(scale, { toValue: 1, friction: 6, useNativeDriver: true }),
        calmLoop(1.02, 1600),
      ]);
    } else {
      anim = Animated.parallel([calmLoop(1.02, 1800), glowLoop]);
    }
    anim.start();
    return () => anim?.stop();
  }, [active, glow, reduceMotion, scale, state]);

  const imageStyle: ImageStyle = {
    width: size,
    height: size,
    borderRadius: circular ? size / 2 : size * 0.18,
  };

  return (
    <View style={[{ width: size, height: size }, style]}>
      <Animated.View
        style={[
          styles.glow,
          {
            width: size + 10,
            height: size + 10,
            borderRadius: (size + 10) / 2,
            opacity: glow,
            left: -5,
            top: -5,
          },
        ]}
      />
      <Animated.View style={{ transform: [{ scale }] }}>
        <Image source={avatarSourceForState(state)} style={imageStyle} />
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  glow: {
    position: 'absolute',
    backgroundColor: colors.accentGlow,
  },
});
