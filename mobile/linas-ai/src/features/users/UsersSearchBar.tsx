import { StyleSheet, TextInput, View } from 'react-native';

import { AppIcon, feather } from '../../components/AppIcon';
import { useI18n } from '../../i18n/LanguageContext';
import { HIT, colors, fonts, radii } from '../../theme';

type Props = {
  value: string;
  onChange: (next: string) => void;
};

export function UsersSearchBar({ value, onChange }: Props) {
  const { tr } = useI18n();
  return (
    <View style={styles.wrap}>
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
  );
}

const styles = StyleSheet.create({
  wrap: {
    minHeight: HIT - 4,
    borderRadius: 16,
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
});
