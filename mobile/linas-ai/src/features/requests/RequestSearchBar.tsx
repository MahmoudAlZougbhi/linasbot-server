import { Pressable, StyleSheet, TextInput, View } from 'react-native';

import { AppIcon, feather } from '../../components/AppIcon';
import { HIT, fonts, radii, useTheme } from '../../theme';

type Props = {
  value: string;
  onChange: (next: string) => void;
  filterActive: boolean;
  onOpenFilter: () => void;
};

export function RequestSearchBar({ value, onChange, filterActive, onOpenFilter }: Props) {
  const { colors } = useTheme();
  return (
    <View style={styles.row}>
      <View style={[styles.search, { backgroundColor: colors.input, borderColor: colors.border }]}>
        <AppIcon icon={feather('search')} size={16} color={colors.textDim} />
        <TextInput
          value={value}
          onChangeText={onChange}
          placeholder="Search name, phone, or request"
          placeholderTextColor={colors.textDim}
          style={[styles.input, { color: colors.text }]}
          accessibilityLabel="Search name, phone, or request"
          autoCorrect={false}
          autoCapitalize="none"
        />
      </View>
      <Pressable
        onPress={onOpenFilter}
        style={[styles.filter, { backgroundColor: colors.surface, borderColor: colors.border }]}
        accessibilityRole="button"
        accessibilityLabel="Filter requests"
      >
        <AppIcon icon={feather('sliders')} size={18} color={colors.text} />
        {filterActive ? <View style={[styles.dot, { backgroundColor: colors.accent }]} /> : null}
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 },
  search: {
    flex: 1,
    minHeight: HIT,
    borderRadius: radii.sm,
    borderWidth: 1,
    paddingHorizontal: 12,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  input: { flex: 1, minHeight: HIT - 8, paddingVertical: 8, fontFamily: fonts.body, fontSize: 15 },
  filter: {
    width: HIT,
    height: HIT,
    borderRadius: radii.sm,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  dot: {
    position: 'absolute',
    top: 8,
    right: 8,
    width: 8,
    height: 8,
    borderRadius: 4,
  },
});
