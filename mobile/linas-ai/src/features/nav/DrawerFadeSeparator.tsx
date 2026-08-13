import { StyleSheet, View } from 'react-native';

import { LinasSparkleIcon } from '../../components/LinasSparkleIcon';

const FADE_STEPS = 10;

type Props = {
  lineColor: string;
  starColor: string;
};

/** Horizontal rule that fades toward the edges with a centered Linas sparkle. */
export function DrawerFadeSeparator({ lineColor, starColor }: Props) {
  const opacities = Array.from({ length: FADE_STEPS }, (_, i) => (i + 1) / FADE_STEPS);

  return (
    <View style={styles.row}>
      <View style={styles.side}>
        {opacities.map((opacity, index) => (
          <View
            key={`l-${index}`}
            style={[styles.segment, { backgroundColor: lineColor, opacity }]}
          />
        ))}
      </View>
      <LinasSparkleIcon size={10} color={starColor} />
      <View style={styles.side}>
        {opacities.map((opacity, index) => (
          <View
            key={`r-${index}`}
            style={[
              styles.segment,
              { backgroundColor: lineColor, opacity: opacities[FADE_STEPS - 1 - index] },
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
});
