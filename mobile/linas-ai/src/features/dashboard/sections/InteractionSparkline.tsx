import { StyleSheet, Text, View } from 'react-native';

import { fonts, spacing, useTheme } from '../../../theme';

type Point = { date: string; interactions: number };

type Props = { points: Point[] };

export function InteractionSparkline({ points }: Props) {
  const { colors } = useTheme();
  const max = Math.max(1, ...points.map((p) => p.interactions));
  const total = points.reduce((sum, p) => sum + p.interactions, 0);
  return (
    <View
      style={styles.wrap}
      accessibilityRole="image"
      accessibilityLabel={`Interaction trend. ${points.length} days. Total ${total} interactions.`}
    >
      <Text style={[styles.label, { color: colors.textDim }]}>Interactions over time</Text>
      <View style={styles.bars}>
        {points.slice(-14).map((p) => (
          <View key={p.date} style={styles.barCol}>
            <View
              style={[
                styles.bar,
                {
                  height: Math.max(4, Math.round((p.interactions / max) * 56)),
                  backgroundColor: colors.accent,
                },
              ]}
            />
          </View>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { marginTop: spacing.sm, gap: 6 },
  label: { fontFamily: fonts.body, fontSize: 12 },
  bars: { flexDirection: 'row', alignItems: 'flex-end', gap: 3, height: 60 },
  barCol: { flex: 1, alignItems: 'center', justifyContent: 'flex-end' },
  bar: { width: '100%', borderRadius: 3, minHeight: 4 },
});
