/**
 * Cold open: dark forest green + centered white sparkle + mint dot.
 *
 * Native splash (app.json) uses the same splash-native.png on #083A37 so the
 * first paint does not flash a different (warm cream) screen.
 *
 * Always dismisses: min display, then auth-ready, or maxHoldMs — whichever
 * comes first after the minimum. Never wait on network.
 */
import * as SplashScreen from 'expo-splash-screen';
import { useEffect, useRef, useState } from 'react';
import {
  AccessibilityInfo,
  Animated,
  Easing,
  Image,
  StyleSheet,
} from 'react-native';

import { bootSplashTokens as t, splashExitDelayMs } from './bootSplashTokens';
import splashMark from '../../../assets/splash-native.png';

type Props = {
  /** True once auth/session init has finished (token + user hydration). */
  appReady: boolean;
  onDone: () => void;
};

export function BootSplash({ appReady, onDone }: Props) {
  const [reduceMotion, setReduceMotion] = useState(false);
  const hidden = useRef(false);
  const mountedAt = useRef(Date.now());
  const exiting = useRef(false);
  const finished = useRef(false);
  const screenOpacity = useRef(new Animated.Value(1)).current;

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

  function complete() {
    if (finished.current) return;
    finished.current = true;
    hideNativeSplash();
    onDone();
  }

  useEffect(() => {
    // If onLayout never fires (some native views), still release the OS splash.
    const fallback = setTimeout(() => hideNativeSplash(), 80);
    return () => clearTimeout(fallback);
  }, []);

  useEffect(() => {
    if (exiting.current) return;

    const minMs = reduceMotion ? t.minDisplayReducedMs : t.minDisplayMs;
    const elapsed = Date.now() - mountedAt.current;
    const waitMs = splashExitDelayMs(appReady, elapsed, minMs, t.maxHoldMs);

    let failsafe: ReturnType<typeof setTimeout> | undefined;
    const timer = setTimeout(() => {
      if (exiting.current) return;
      exiting.current = true;
      hideNativeSplash();

      const fadeMs = reduceMotion ? 0 : t.exitFadeMs;
      if (fadeMs <= 0) {
        complete();
        return;
      }

      Animated.timing(screenOpacity, {
        toValue: 0,
        duration: fadeMs,
        easing: Easing.out(Easing.cubic),
        useNativeDriver: true,
      }).start(() => {
        complete();
      });
      failsafe = setTimeout(complete, fadeMs + 80);
    }, waitMs);

    return () => {
      clearTimeout(timer);
      if (failsafe) clearTimeout(failsafe);
    };
  }, [appReady, onDone, reduceMotion, screenOpacity]);

  return (
    <Animated.View
      style={[styles.root, { opacity: screenOpacity }]}
      importantForAccessibility="no-hide-descendants"
      accessibilityElementsHidden
      onLayout={() => {
        if (typeof requestAnimationFrame === 'function') {
          requestAnimationFrame(() => hideNativeSplash());
        } else {
          hideNativeSplash();
        }
      }}
    >
      <Image
        source={splashMark}
        style={styles.mark}
        resizeMode="contain"
        fadeDuration={0}
        accessible={false}
        importantForAccessibility="no"
      />
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: t.background,
    alignItems: 'center',
    justifyContent: 'center',
  },
  mark: {
    width: t.markSize,
    height: t.markSize,
  },
});
