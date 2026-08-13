import { StyleSheet, Text, View } from 'react-native';

const FADE_STEPS = 10;

type Props = {
  color: string;
};

/** Teal accent line that fades toward the edges with a centered sparkle. */
export function DrawerFadeSeparator({ color }: Props) {
  const opacities = Array.from({ length: FADE_STEPS }, (_, i) => (i + 1) / FADE_STEPS);

  return (
    <View style={styles.row}>
      <View style={styles.side}>
        {opacities.map((opacity, index) => (
          <View
            key={`l-${index}`}
            style={[styles.segment, { backgroundColor: color, opacity }]}
          />
        ))}
      </View>
      <Text style={[styles.sparkle, { color }]}>✦</Text>
      <View style={styles.side}>
        {opacities.map((opacity, index) => (
          <View
            key={`r-${index}`}
            style={[
              styles.segment,
              { backgroundColor: color, opacity: opacities[FADE_STEPS - 1 - index] },
            ]}
          />
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  side: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    height: StyleSheet.hairlineWidth,
  },
  segment: {
    flex: 1,
    height: StyleSheet.hairlineWidth,
  },
  sparkle: {
    fontSize: 10,
    lineHeight: 12,
  },
});
