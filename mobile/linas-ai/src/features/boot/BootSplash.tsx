import { useEffect, useRef } from 'react';
import { Animated, StyleSheet, Text, View } from 'react-native';

import { BrandMark } from '../../components/BrandMark';
import { GradientBackground } from '../../components/GradientBackground';
import { colors, fonts } from '../../theme';
import { LinasAvatar } from '../linas/LinasAvatar';

type Props = {
  onDone: () => void;
};

export function BootSplash({ onDone }: Props) {
  const opacity = useRef(new Animated.Value(0)).current;
  const scale = useRef(new Animated.Value(0.92)).current;
  const progress = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.parallel([
      Animated.timing(opacity, { toValue: 1, duration: 420, useNativeDriver: true }),
      Animated.spring(scale, { toValue: 1, friction: 7, useNativeDriver: true }),
      Animated.timing(progress, { toValue: 1, duration: 1000, useNativeDriver: false }),
    ]).start();
    const t = setTimeout(onDone, 1150);
    return () => clearTimeout(t);
  }, [onDone, opacity, progress, scale]);

  const width = progress.interpolate({ inputRange: [0, 1], outputRange: ['8%', '100%'] });

  return (
    <GradientBackground>
      <View style={styles.center}>
        <Animated.View style={[styles.block, { opacity, transform: [{ scale }] }]}>
          <LinasAvatar state="welcome" size={120} />
          <BrandMark size="lg" showWordmark showMark={false} style={styles.mark} />
          <View style={styles.track}>
            <Animated.View style={[styles.fill, { width }]} />
          </View>
          <Text style={styles.hint}>Opening Linas AI…</Text>
        </Animated.View>
      </View>
    </GradientBackground>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 32 },
  block: { alignItems: 'center', width: '100%' },
  mark: { marginTop: 8 },
  track: {
    marginTop: 28,
    width: '72%',
    maxWidth: 240,
    height: 6,
    borderRadius: 999,
    backgroundColor: colors.progressTrack,
    overflow: 'hidden',
  },
  fill: { height: '100%', backgroundColor: colors.progressFill, borderRadius: 999 },
  hint: {
    marginTop: 16,
    color: colors.textDim,
    fontFamily: fonts.body,
    fontSize: 13,
    textAlign: 'center',
  },
});
