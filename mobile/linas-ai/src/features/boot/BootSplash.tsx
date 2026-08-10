/**
 * ChatGPT-like cold open: branded star logo, short hold, then chat.
 * Native splash (app.json) matches this surface so hideAsync is seamless.
 */
import * as SplashScreen from 'expo-splash-screen';
import { useEffect, useRef, useState } from 'react';
import {
  AccessibilityInfo,
  Animated,
  Image,
  StyleSheet,
  Text,
  View,
  useColorScheme,
} from 'react-native';

import { fonts } from '../../theme';

type Props = {
  onDone: () => void;
};

/** Matches adaptive icon / native splash brand plate. */
const BRAND_EMERALD = '#0B3D34';
const BRAND_EMERALD_LIGHT = '#F3FAF8';
const HOLD_MS = 640;
const HOLD_REDUCED_MS = 120;
const FADE_MS = 380;

export function BootSplash({ onDone }: Props) {
  const scheme = useColorScheme();
  const dark = scheme !== 'light';
  const opacity = useRef(new Animated.Value(0)).current;
  const scale = useRef(new Animated.Value(0.94)).current;
  const [reduceMotion, setReduceMotion] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void AccessibilityInfo.isReduceMotionEnabled().then((v) => {
      if (!cancelled) setReduceMotion(v);
    });
    const sub = AccessibilityInfo.addEventListener('reduceMotionChanged', setReduceMotion);
    return () => {
      cancelled = true;
      sub.remove();
    };
  }, []);

  useEffect(() => {
    let finished = false;
    const finish = () => {
      if (finished) return;
      finished = true;
      onDone();
    };

    void SplashScreen.hideAsync().catch(() => {
      // Expo Go / web may already have hidden — continue branded hold.
    });

    if (reduceMotion) {
      opacity.setValue(1);
      scale.setValue(1);
      const t = setTimeout(finish, HOLD_REDUCED_MS);
      return () => clearTimeout(t);
    }

    Animated.parallel([
      Animated.timing(opacity, { toValue: 1, duration: FADE_MS, useNativeDriver: true }),
      Animated.spring(scale, { toValue: 1, friction: 8, tension: 80, useNativeDriver: true }),
    ]).start();

    const t = setTimeout(finish, HOLD_MS);
    return () => clearTimeout(t);
  }, [onDone, opacity, reduceMotion, scale]);

  const bg = dark ? BRAND_EMERALD : BRAND_EMERALD_LIGHT;
  const wordColor = dark ? '#F2FAF8' : BRAND_EMERALD;

  return (
    <View
      style={[styles.root, { backgroundColor: bg }]}
      accessibilityRole="image"
      accessibilityLabel="Linas AI"
    >
      <Animated.View style={[styles.block, { opacity, transform: [{ scale }] }]}>
        <Image
          source={require('../../../assets/splash-icon.png')}
          style={styles.logo}
          resizeMode="contain"
          accessibilityIgnoresInvertColors
        />
        <Text style={[styles.word, { color: wordColor }]}>Linas AI</Text>
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  block: { alignItems: 'center', gap: 18 },
  logo: {
    width: 112,
    height: 112,
    borderRadius: 28,
  },
  word: {
    fontFamily: fonts.display,
    fontSize: 28,
    letterSpacing: 0.2,
    textAlign: 'center',
  },
});
