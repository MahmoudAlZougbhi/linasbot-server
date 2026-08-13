/**
 * Branded cold open: sparkle mark + wordmark + AI loading line.
 *
 * Native splash (app.json) stays logo-free warm #FBFAFA — Android 12+ would
 * otherwise circular-mask splash-icon into a different first shape. This
 * surface is the only logo the user should see.
 */
import * as SplashScreen from 'expo-splash-screen';
import { useEffect, useRef, useState } from 'react';
import {
  AccessibilityInfo,
  Animated,
  Easing,
  Platform,
  StyleSheet,
  Text,
  useWindowDimensions,
  View,
} from 'react-native';

import { LinasSparkleMark } from '../../components/LinasSparkleMark';
import { BootSplashAiLine } from './BootSplashAiLine';
import { bootSplashTokens as t } from './bootSplashTokens';

type Props = {
  /** True once auth/session init has finished (token + user hydration). */
  appReady: boolean;
  onDone: () => void;
};

const displayFont = Platform.select({
  ios: 'System',
  android: 'sans-serif-medium',
  default: 'System',
});

export function BootSplash({ appReady, onDone }: Props) {
  const { height: windowHeight } = useWindowDimensions();
  const [reduceMotion, setReduceMotion] = useState(false);
  const hidden = useRef(false);
  const mountedAt = useRef(Date.now());
  const exiting = useRef(false);

  const screenOpacity = useRef(new Animated.Value(1)).current;
  const contentOpacity = useRef(new Animated.Value(0)).current;
  const contentScale = useRef(new Animated.Value(t.entranceScaleFrom)).current;
  const lineOpacity = useRef(new Animated.Value(0)).current;

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
    const opacityAnim = Animated.timing(contentOpacity, {
      toValue: 1,
      duration: t.entranceOpacityMs,
      easing: Easing.out(Easing.cubic),
      useNativeDriver: true,
    });
    const scaleAnim = Animated.timing(contentScale, {
      toValue: 1,
      duration: t.entranceScaleMs,
      easing: Easing.out(Easing.cubic),
      useNativeDriver: true,
    });
    const lineAnim = Animated.timing(lineOpacity, {
      toValue: 1,
      duration: t.entranceOpacityMs,
      delay: t.loadingDelayMs,
      easing: Easing.out(Easing.cubic),
      useNativeDriver: true,
    });

    if (reduceMotion) {
      contentOpacity.setValue(1);
      contentScale.setValue(1);
      lineOpacity.setValue(1);
      return;
    }

    Animated.parallel([opacityAnim, scaleAnim]).start();
    lineAnim.start();
    return () => {
      opacityAnim.stop();
      scaleAnim.stop();
      lineAnim.stop();
    };
  }, [contentOpacity, contentScale, lineOpacity, reduceMotion]);

  function hideNativeSplash() {
    if (hidden.current) return;
    hidden.current = true;
    void SplashScreen.hideAsync().catch(() => {
      // Expo Go / web may already have hidden — continue branded hold.
    });
  }

  useEffect(() => {
    if (!appReady || exiting.current) return;

    const minMs = reduceMotion ? t.minDisplayReducedMs : t.minDisplayMs;
    const elapsed = Date.now() - mountedAt.current;
    const waitMs = Math.max(0, minMs - elapsed);

    const timer = setTimeout(() => {
      if (exiting.current) return;
      exiting.current = true;

      Animated.timing(screenOpacity, {
        toValue: 0,
        duration: t.exitFadeMs,
        easing: Easing.out(Easing.cubic),
        useNativeDriver: true,
      }).start(({ finished }) => {
        if (finished) onDone();
      });
    }, waitMs);

    return () => clearTimeout(timer);
  }, [appReady, onDone, reduceMotion, screenOpacity]);

  const logoTop = windowHeight * t.logoCenterYRatio - t.sparkleHeight / 2;

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
      <Animated.View
        style={[
          styles.content,
          {
            top: logoTop,
            opacity: contentOpacity,
            transform: [{ scale: contentScale }],
          },
        ]}
      >
        <View style={styles.glowWrap}>
          <View style={styles.glow} />
          <LinasSparkleMark
            size={t.sparkleWidth}
            color={t.sparkleColor}
            dotColor={t.onlineDotColor}
            dotSize={t.onlineDotSize}
            dotGap={t.onlineDotGap}
          />
        </View>
        <Text style={styles.word}>Linas AI</Text>
        <Animated.View style={[styles.lineWrap, { opacity: lineOpacity }]}>
          <BootSplashAiLine reduceMotion={reduceMotion} />
        </Animated.View>
      </Animated.View>
    </Animated.View>
  );
}

const glowDiameter = (t.glowBlurMin + t.glowBlurMax) / 2 * 2;

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: t.background,
  },
  content: {
    position: 'absolute',
    left: 0,
    right: 0,
    alignItems: 'center',
  },
  glowWrap: {
    alignItems: 'center',
    justifyContent: 'center',
    width: glowDiameter,
    height: glowDiameter,
  },
  glow: {
    position: 'absolute',
    width: glowDiameter,
    height: glowDiameter,
    borderRadius: glowDiameter / 2,
    backgroundColor: t.glowColor,
    opacity: t.glowOpacity,
    ...Platform.select({
      ios: {
        shadowColor: t.glowColor,
        shadowOpacity: 0.55,
        shadowRadius: (t.glowBlurMin + t.glowBlurMax) / 2,
        shadowOffset: { width: 0, height: 0 },
      },
      android: { elevation: 0 },
      default: {},
    }),
  },
  word: {
    marginTop: t.nameBelowLogo,
    color: t.appNameColor,
    fontFamily: displayFont,
    fontSize: t.appNameSize,
    fontWeight: t.appNameWeight,
    letterSpacing: t.appNameLetterSpacing,
    textAlign: 'center',
  },
  lineWrap: {
    marginTop: t.lineBelowName,
  },
});
