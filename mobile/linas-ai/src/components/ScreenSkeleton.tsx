import { useEffect, useRef } from 'react';
import { Animated, Easing, StyleSheet, View } from 'react-native';

import { useReduceMotion } from '../hooks/useReduceMotion';
import { radii, spacing, useTheme } from '../theme';

export type SkeletonVariant = 'list' | 'inbox' | 'cards' | 'form' | 'chart';

type Props = {
  variant?: SkeletonVariant;
  rows?: number;
};

/**
 * Layout-matched placeholders for cold opens. Uses existing track/input tokens only.
 * Header/chrome stay outside this component.
 */
export function ScreenSkeleton({ variant = 'list', rows }: Props) {
  const { colors } = useTheme();
  const pulse = usePulse();
  const fill = colors.progressTrack;
  const bone = (key: string, style: object) => (
    <Animated.View
      key={key}
      style={[styles.bone, { backgroundColor: fill, opacity: pulse }, style]}
    />
  );

  if (variant === 'inbox') {
    const n = rows ?? 7;
    return (
      <View style={styles.wrap} accessibilityLabel="Loading" accessibilityRole="progressbar">
        {Array.from({ length: n }, (_, i) => (
          <View key={i} style={styles.inboxRow}>
            {bone(`a${i}`, styles.avatar)}
            <View style={styles.inboxText}>
              {bone(`t${i}`, { height: 12, width: '58%' })}
              {bone(`s${i}`, { height: 10, width: '82%', marginTop: 8 })}
            </View>
            {bone(`m${i}`, { height: 10, width: 36 })}
          </View>
        ))}
      </View>
    );
  }

  if (variant === 'cards') {
    const n = rows ?? 4;
    return (
      <View style={styles.wrap} accessibilityLabel="Loading" accessibilityRole="progressbar">
        {Array.from({ length: n }, (_, i) => (
          <View key={i} style={[styles.card, { borderColor: colors.borderSoft }]}>
            {bone(`c${i}`, { height: 14, width: '40%' })}
            {bone(`d${i}`, { height: 10, width: '72%', marginTop: 10 })}
            {bone(`e${i}`, { height: 10, width: '50%', marginTop: 8 })}
          </View>
        ))}
      </View>
    );
  }

  if (variant === 'form') {
    const n = rows ?? 6;
    return (
      <View style={styles.wrap} accessibilityLabel="Loading" accessibilityRole="progressbar">
        {Array.from({ length: n }, (_, i) => (
          <View key={i} style={styles.field}>
            {bone(`l${i}`, { height: 10, width: '28%' })}
            {bone(`f${i}`, { height: 40, width: '100%', marginTop: 8, borderRadius: radii.md })}
          </View>
        ))}
      </View>
    );
  }

  if (variant === 'chart') {
    return (
      <View style={styles.wrap} accessibilityLabel="Loading" accessibilityRole="progressbar">
        {bone('plan', { height: 88, width: '100%', borderRadius: radii.lg })}
        <View style={styles.grid}>
          {Array.from({ length: 4 }, (_, i) => bone(`g${i}`, styles.gridCell))}
        </View>
        {bone('table', { height: 132, width: '100%', borderRadius: radii.lg })}
        {bone('copilot', { height: 72, width: '100%', borderRadius: radii.lg })}
      </View>
    );
  }

  const n = rows ?? 6;
  return (
    <View style={styles.wrap} accessibilityLabel="Loading" accessibilityRole="progressbar">
      {Array.from({ length: n }, (_, i) =>
        bone(`r${i}`, { height: 56, width: '100%', marginBottom: spacing.sm, borderRadius: radii.md }),
      )}
    </View>
  );
}

function usePulse() {
  const reduceMotion = useReduceMotion();
  const opacity = useRef(new Animated.Value(0.55)).current;
  useEffect(() => {
    opacity.stopAnimation();
    if (reduceMotion) {
      opacity.setValue(0.7);
      return;
    }
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(opacity, {
          toValue: 1,
          duration: 700,
          easing: Easing.inOut(Easing.sin),
          useNativeDriver: true,
        }),
        Animated.timing(opacity, {
          toValue: 0.45,
          duration: 700,
          easing: Easing.inOut(Easing.sin),
          useNativeDriver: true,
        }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [opacity, reduceMotion]);
  return opacity;
}

const styles = StyleSheet.create({
  wrap: { paddingTop: spacing.sm, paddingBottom: spacing.lg },
  bone: { borderRadius: radii.sm },
  inboxRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    minHeight: 64,
    paddingVertical: 10,
  },
  avatar: { width: 40, height: 40, borderRadius: 20 },
  inboxText: { flex: 1 },
  card: {
    borderWidth: 1,
    borderRadius: radii.lg,
    padding: spacing.md,
    marginBottom: spacing.sm,
  },
  field: { marginBottom: spacing.md },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, marginTop: spacing.md, marginBottom: spacing.md },
  gridCell: { width: '47%', height: 72, borderRadius: radii.md, flexGrow: 1 },
});
