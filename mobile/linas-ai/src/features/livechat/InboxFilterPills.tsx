import { Pressable, StyleSheet, Text, View } from 'react-native';

import { fonts, radii, useTheme } from '../../theme';
import type { InboxFilter } from './liveChatTypes';

const PILLS: { id: InboxFilter; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'with_operator', label: 'Human' },
];

type Props = {
  selected: InboxFilter;
  onSelect: (id: InboxFilter) => void;
};

export function InboxFilterPills({ selected, onSelect }: Props) {
  const { colors } = useTheme();
  return (
    <View style={styles.row}>
      {PILLS.map((pill) => {
        const active = selected === pill.id;
        return (
          <Pressable
            key={pill.id}
            onPress={() => onSelect(pill.id)}
            style={[
              styles.pill,
              {
                backgroundColor: active ? colors.accentSoft : colors.surface,
                borderColor: active ? colors.accent : colors.border,
              },
            ]}
            accessibilityRole="button"
            accessibilityLabel={`Filter ${pill.label}`}
            accessibilityState={{ selected: active }}
          >
            <Text
              style={[
                styles.label,
                { color: active ? colors.text : colors.textMuted },
              ]}
            >
              {pill.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', gap: 8, marginBottom: 8 },
  pill: {
    borderRadius: radii.pill,
    borderWidth: 1,
    paddingHorizontal: 16,
    paddingVertical: 8,
    minHeight: 36,
    justifyContent: 'center',
  },
  label: { fontFamily: fonts.bodyMedium, fontSize: 14 },
});
