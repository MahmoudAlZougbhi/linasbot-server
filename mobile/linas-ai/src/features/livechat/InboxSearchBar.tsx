import { StyleSheet, TextInput, View } from 'react-native';

import { AppIcon, feather } from '../../components/AppIcon';
import { HIT, fonts, radii, useTheme } from '../../theme';

type Props = {
  value: string;
  onChange: (next: string) => void;
};

export function InboxSearchBar({ value, onChange }: Props) {
  const { colors } = useTheme();
  return (
    <View
      style={[
        styles.wrap,
        { backgroundColor: colors.input, borderColor: colors.border },
      ]}
    >
      <AppIcon icon={feather('search')} size={16} color={colors.textDim} />
      <TextInput
        value={value}
        onChangeText={onChange}
        placeholder="Search conversations"
        placeholderTextColor={colors.textDim}
        autoCapitalize="none"
        autoCorrect={false}
        style={[styles.input, { color: colors.text }]}
        accessibilityLabel="Search conversations"
      />
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    minHeight: HIT,
    borderRadius: radii.pill,
    borderWidth: 1,
    paddingHorizontal: 16,
    marginBottom: 12,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  input: {
    flex: 1,
    minHeight: HIT - 8,
    paddingVertical: 8,
    fontFamily: fonts.body,
    fontSize: 16,
  },
});
