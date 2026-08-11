import { Ionicons } from '@expo/vector-icons';
import { StyleSheet, Text, View } from 'react-native';

import type { StringKey } from '../../i18n';
import { fonts, radii, spacing, useTheme } from '../../theme';
import { COMMON_FEATURE_KEYS } from './planCatalog';

type Props = {
  tr: (key: StringKey) => string;
};

export function CommonFeaturesCard({ tr }: Props) {
  const { colors } = useTheme();
  return (
    <View style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}>
      <Text style={[styles.title, { color: colors.accentDeep }]}>{tr('subCommonTitle')}</Text>
      {COMMON_FEATURE_KEYS.map((key) => (
        <View key={key} style={styles.row}>
          <Ionicons name="checkmark-circle" size={18} color={colors.accent} />
          <Text style={[styles.text, { color: colors.text }]}>{tr(key)}</Text>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: radii.lg,
    borderWidth: 1,
    padding: spacing.lg,
    gap: 8,
  },
  title: { fontFamily: fonts.display, fontSize: 17, marginBottom: 4 },
  row: { flexDirection: 'row', alignItems: 'flex-start', gap: 8 },
  text: { flex: 1, fontFamily: fonts.body, fontSize: 13, lineHeight: 18 },
});
