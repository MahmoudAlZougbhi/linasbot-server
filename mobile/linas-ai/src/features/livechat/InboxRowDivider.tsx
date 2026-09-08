import { StyleSheet, View } from 'react-native';

const STEPS = 10;
const LINE_HEIGHT = 1;
const EDGE_INSET = 28;

/** Inset rule that is solid in the middle and fades out left/right — not full-bleed. */
export function InboxRowDivider({ color }: { color: string }) {
  const fadeIn = Array.from({ length: STEPS }, (_, i) => (STEPS <= 1 ? 1 : i / (STEPS - 1)));

  return (
    <View style={styles.wrap}>
      <View style={styles.side}>
        {fadeIn.map((opacity, index) => (
          <View key={`l-${index}`} style={[styles.segment, { backgroundColor: color, opacity }]} />
        ))}
      </View>
      <View style={styles.side}>
        {fadeIn.map((opacity, index) => (
          <View
            key={`r-${index}`}
            style={[styles.segment, { backgroundColor: color, opacity: fadeIn[STEPS - 1 - index] }]}
          />
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    flexDirection: 'row',
    alignItems: 'center',
    marginHorizontal: EDGE_INSET,
    height: LINE_HEIGHT,
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
