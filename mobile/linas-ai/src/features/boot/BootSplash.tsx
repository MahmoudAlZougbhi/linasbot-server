import { useEffect, useRef } from 'react';
import { Animated, StyleSheet, Text, View } from 'react-native';

import { BrandMark } from '../../components/BrandMark';
import { GradientBackground } from '../../components/GradientBackground';
import { colors, fonts } from '../../theme';

type Props = {
  onDone: () => void;
};

export function BootSplash({ onDone }: Props) {
  const opacity = useRef(new Animated.Value(0)).current;
  const scale = useRef(new Animated.Value(0.92)).current;

  useEffect(() => {
    Animated.parallel([
      Animated.timing(opacity, { toValue: 1, duration: 480, useNativeDriver: true }),
      Animated.spring(scale, { toValue: 1, friction: 7, useNativeDriver: true }),
    ]).start();
    const t = setTimeout(onDone, 1100);
    return () => clearTimeout(t);
  }, [onDone, opacity, scale]);

  return (
    <GradientBackground>
      <View style={styles.center}>
        <Animated.View style={{ opacity, transform: [{ scale }] }}>
          <BrandMark size="lg" showWordmark />
          <Text style={styles.hint}>Opening your workspace…</Text>
        </Animated.View>
      </View>
    </GradientBackground>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 32 },
  hint: {
    marginTop: 28,
    color: colors.textDim,
    fontFamily: fonts.body,
    fontSize: 14,
    textAlign: 'center',
  },
});
