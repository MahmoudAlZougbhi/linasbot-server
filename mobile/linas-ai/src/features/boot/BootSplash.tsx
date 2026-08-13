/**
 * Branded cold open: sparkle mark + wordmark + AI shimmer line, short hold, then chat.
 *
 * Native splash (app.json) stays solid emerald with no logo — Android 12+ would
 * otherwise circular-mask splash-icon into a different first shape. This
 * surface is the only logo the user should see.
 */
import * as SplashScreen from 'expo-splash-screen';
import { useEffect, useRef, useState } from 'react';
import { AccessibilityInfo, StyleSheet, Text, View } from 'react-native';

import { LinasSparkleMark } from '../../components/LinasSparkleMark';
import { fonts, lightColors } from '../../theme';
import { BootSplashAiLine } from './BootSplashAiLine';

type Props = {
  onDone: () => void;
};

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
      <View style={styles.glowWrap}>
        <View style={styles.glow} />
        <LinasSparkleMark size={58} color={lightColors.accent} dotColor={lightColors.accentMid} />
      </View>
      <Text style={styles.word}>Linas AI</Text>
      <BootSplashAiLine reduceMotion={reduceMotion} />
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: lightColors.bgElevated,
  },
  glowWrap: {
    alignItems: 'center',
    justifyContent: 'center',
    width: 220,
    height: 220,
    marginBottom: 6,
  },
  glow: {
    position: 'absolute',
    width: 220,
    height: 220,
    borderRadius: 110,
    backgroundColor: lightColors.mintSoft,
    opacity: 0.42,
  },
  word: {
    color: lightColors.text,
    fontFamily: fonts.display,
    fontSize: 28,
    fontWeight: '700',
    letterSpacing: 0.2,
    textAlign: 'center',
  },
});
