import { StyleSheet, View } from 'react-native';

import { LinasSparkleIcon } from '../../components/LinasSparkleIcon';

const FADE_STEPS = 12;
const SPARKLE_SIZE = 12;
const SPARKLE_GAP = 6;
const LINE_HEIGHT = 1;

type Props = {
  lineColor: string;
  starColor: string;
};

/** Horizontal rule that fades toward the edges with a centered Linas sparkle. */
export function DrawerFadeSeparator({ lineColor, starColor }: Props) {
  const opacities = Array.from({ length: FADE_STEPS }, (_, i) =>
    FADE_STEPS <= 1 ? 1 : i / (FADE_STEPS - 1),
  );

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
      <LinasSparkleIcon size={SPARKLE_SIZE} color={starColor} />
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
    gap: SPARKLE_GAP,
  },
  side: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    height: LINE_HEIGHT,
  },
  segment: {
    flex: 1,
    height: LINE_HEIGHT,
  },
});
