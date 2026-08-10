/**
 * ChatGPT-like cold open: branded star + wordmark, short hold, then chat.
 *
 * Native splash (app.json) is solid emerald with no logo — Android 12+ would
 * otherwise circular-mask splash-icon.png into a different first shape. This
 * surface is the only logo the user should see.
 */
import * as SplashScreen from 'expo-splash-screen';
import { useEffect, useRef, useState } from 'react';
import {
  AccessibilityInfo,
  Image,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { fonts } from '../../theme';

type Props = {
  onDone: () => void;
};

/** Matches native splash background (app.json / splash-native.png). */
const BRAND_EMERALD = '#0B3D34';
const HOLD_MS = 640;
const HOLD_REDUCED_MS = 120;

export function BootSplash({ onDone }: Props) {
  const [reduceMotion, setReduceMotion] = useState(false);
  const hidden = useRef(false);

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

  function hideNativeSplash() {
    if (hidden.current) return;
    hidden.current = true;
    void SplashScreen.hideAsync().catch(() => {
      // Expo Go / web may already have hidden — continue branded hold.
    });
  }

  useEffect(() => {
    let finished = false;
    const finish = () => {
      if (finished) return;
      finished = true;
      onDone();
    };

    // Fallback if onLayout is delayed; prefer onLayout so the star is painted first.
    const raf =
      typeof requestAnimationFrame === 'function'
        ? requestAnimationFrame(() => hideNativeSplash())
        : (hideNativeSplash(), 0);

    const t = setTimeout(finish, reduceMotion ? HOLD_REDUCED_MS : HOLD_MS);
    return () => {
      if (typeof cancelAnimationFrame === 'function' && raf) cancelAnimationFrame(raf);
      clearTimeout(t);
    };
  }, [onDone, reduceMotion]);

  return (
    <View
      style={styles.root}
      accessibilityRole="image"
      accessibilityLabel="Linas AI"
      onLayout={hideNativeSplash}
    >
      <View style={styles.block}>
        <Image
          source={require('../../../assets/splash-icon.png')}
          style={styles.logo}
          resizeMode="contain"
          accessibilityIgnoresInvertColors
        />
        <Text style={styles.word}>Linas AI</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: BRAND_EMERALD,
  },
  block: { alignItems: 'center', gap: 18 },
  logo: {
    width: 112,
    height: 112,
    borderRadius: 28,
  },
  word: {
    color: '#F2FAF8',
    fontFamily: fonts.display,
    fontSize: 28,
    letterSpacing: 0.2,
    textAlign: 'center',
  },
});
