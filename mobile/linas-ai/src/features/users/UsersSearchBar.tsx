import { Pressable, StyleSheet, TextInput, View } from 'react-native';

import { AppIcon, feather } from '../../components/AppIcon';
import { useI18n } from '../../i18n/LanguageContext';
import { HIT, colors, fonts, radii } from '../../theme';

type Props = {
  value: string;
  onChange: (next: string) => void;
  onAdd: () => void;
  addDisabled?: boolean;
};

/** Search + teal square plus — same list chrome as Knowledge / AI Setup. */
export function UsersSearchBar({ value, onChange, onAdd, addDisabled }: Props) {
  const { tr } = useI18n();
  return (
    <View style={styles.row}>
      <View style={styles.search}>
        <AppIcon icon={feather('search')} size={16} color={colors.textDim} />
        <TextInput
          value={value}
          onChangeText={onChange}
          placeholder={tr('usersSearch')}
          placeholderTextColor={colors.textDim}
          autoCapitalize="none"
          autoCorrect={false}
          style={styles.input}
          accessibilityLabel={tr('usersSearch')}
        />
      </View>
      <Pressable
        onPress={onAdd}
        disabled={addDisabled}
        accessibilityRole="button"
        accessibilityLabel={tr('usersAdd')}
        style={({ pressed }) => [styles.addSq, (pressed || addDisabled) && styles.pressed]}
      >
        <AppIcon icon={feather('plus')} size={22} color="#FFFFFF" />
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  search: {
    flex: 1,
    minHeight: HIT - 4,
    borderRadius: radii.md,
    backgroundColor: colors.input,
    borderWidth: 1,
    borderColor: colors.borderSoft,
    paddingHorizontal: 14,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  input: {
    flex: 1,
    minHeight: HIT - 12,
    paddingVertical: 8,
    fontFamily: fonts.body,
    fontSize: 16,
    color: colors.text,
  },
  addSq: {
    width: 48,
    height: 48,
    borderRadius: radii.md,
    backgroundColor: colors.accent,
    alignItems: 'center',
    justifyContent: 'center',
  },
  pressed: { opacity: 0.55 },
});
