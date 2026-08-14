import { Pressable, StyleSheet, Text, View } from 'react-native';

import { fonts, radii, spacing, useTheme } from '../../theme';
import { bucketCounts } from './requestsFormat';
import type { StatusBucket } from './requestsTypes';

const BUCKETS: { id: StatusBucket; label: string }[] = [
  { id: 'new', label: 'New' },
  { id: 'in_progress', label: 'In progress' },
  { id: 'done', label: 'Done' },
];

type Props = {
  counts: Record<string, number>;
  selected: StatusBucket | null;
  onSelect: (id: StatusBucket | null) => void;
};

export function RequestSummaryCards({ counts, selected, onSelect }: Props) {
  const { colors } = useTheme();
  const buckets = bucketCounts(counts);
  return (
    <View style={styles.row}>
      {BUCKETS.map((bucket) => {
        const active = selected === bucket.id;
        return (
          <Pressable
            key={bucket.id}
            onPress={() => onSelect(active ? null : bucket.id)}
            style={[
              styles.card,
              {
                backgroundColor: colors.surface,
                borderColor: active ? colors.accent : colors.border,
              },
            ]}
            accessibilityRole="button"
            accessibilityLabel={`${bucket.label} ${buckets[bucket.id]}`}
            accessibilityState={{ selected: active }}
          >
            <Text style={[styles.count, { color: colors.accent }]}>{buckets[bucket.id]}</Text>
            <Text style={[styles.label, { color: colors.textMuted }]}>{bucket.label}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', gap: 10, marginBottom: spacing.md },
  card: {
    flex: 1,
    borderWidth: 1,
    borderRadius: radii.sm,
    paddingVertical: spacing.md,
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 72,
  },
  count: { fontFamily: fonts.display, fontSize: 28, fontWeight: '700', lineHeight: 34 },
  label: { fontFamily: fonts.body, fontSize: 13, marginTop: 2 },
});
