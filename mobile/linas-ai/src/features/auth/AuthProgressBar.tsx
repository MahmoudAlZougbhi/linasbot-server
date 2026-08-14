import { StyleSheet, View } from 'react-native';

import { colors, radii } from '../../theme';

type Props = {
  filled: 1 | 2 | 3;
};

/** Three-segment signup progress — filled segments use brand teal. */
export function AuthProgressBar({ filled }: Props) {
  return (
    <View style={styles.row}>
      {([1, 2, 3] as const).map((n) => (
        <View key={n} style={[styles.seg, n <= filled ? styles.on : styles.off]} />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', gap: 8, width: '100%', marginTop: 18, marginBottom: 10 },
  seg: { flex: 1, height: 4, borderRadius: radii.pill },
  on: { backgroundColor: colors.accent },
  off: { backgroundColor: colors.progressTrack },
});
