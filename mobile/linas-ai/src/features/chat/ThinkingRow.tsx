import { useEffect, useRef, useState } from 'react';
import { AccessibilityInfo, Animated, Easing, StyleSheet, View } from 'react-native';

import { LinasStarMark } from '../../components/LinasStarMark';
import { aiMessageColStyle, aiMessageRowStyle, textDirectionStyle } from '../../lib/textDirection';
import { fonts, spacing, typography, useTheme } from '../../theme';

type Props = {
  label: string;
};

/**
 * Linas-side Thinking… placeholder for the live turn slot.
 * Replaced by streamed liveText in the same footer when deltas start.
 */
export function ThinkingRow({ label }: Props) {
  const { colors } = useTheme();
  const dirStyle = textDirectionStyle(label);
  const opacity = useRef(new Animated.Value(1)).current;
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
    opacity.stopAnimation();
    if (reduceMotion) {
      opacity.setValue(1);
      return;
    }
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(opacity, {
          toValue: 0.35,
          duration: 700,
          easing: Easing.inOut(Easing.sin),
          useNativeDriver: true,
        }),
        Animated.timing(opacity, {
          toValue: 1,
          duration: 700,
          easing: Easing.inOut(Easing.sin),
          useNativeDriver: true,
        }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [opacity, reduceMotion]);

  return (
    <View
      style={[styles.row, styles.rowAi, aiMessageRowStyle(label)]}
      accessibilityLiveRegion="polite"
      accessibilityRole="text"
      accessibilityLabel={label}
    >
      <View style={[styles.col, styles.colAi, aiMessageColStyle(label)]}>
        <View style={styles.aiLabelRow}>
          <LinasStarMark size={12} labeled label="Linas" labelColor={colors.text} />
        </View>
        <Animated.Text style={[styles.text, { color: colors.textMuted, opacity }, dirStyle]}>
          {label}
        </Animated.Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    marginBottom: spacing.md,
  },
  rowAi: { alignSelf: 'flex-start', maxWidth: '88%' },
  col: { flexShrink: 1 },
  colAi: { alignItems: 'flex-start' },
  aiLabelRow: {
    marginBottom: 4,
  },
  text: {
    ...typography.chatAi,
    fontFamily: fonts.body,
    paddingHorizontal: 2,
    paddingVertical: 2,
  },
});
