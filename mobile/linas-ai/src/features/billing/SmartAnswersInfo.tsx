import { StyleSheet, Text, View } from 'react-native';

import { AppIcon, ion } from '../../components/AppIcon';
import type { StringKey } from '../../i18n';
import { fonts, radii, spacing, useTheme } from '../../theme';

type Props = {
  tr: (key: StringKey) => string;
  variant: 'current' | 'choose';
};

export function SmartAnswersInfo({ tr, variant }: Props) {
  const { colors } = useTheme();
  return (
    <View style={[styles.banner, { backgroundColor: colors.surfaceAlt }]}>
      <AppIcon icon={ion('information-circle')} size={22} color={colors.accent} />
      {variant === 'choose' ? (
        <View style={styles.copy}>
          <Text style={[styles.title, { color: colors.text }]}>{tr('subSmartAnswersTitle')}</Text>
          <Text style={[styles.body, { color: colors.textMuted }]}>{tr('subSmartAnswersBody')}</Text>
        </View>
      ) : (
        <Text style={[styles.body, { color: colors.textMuted }]}>{tr('subSmartAnswersCurrent')}</Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  banner: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 10,
    borderRadius: radii.md,
    paddingHorizontal: spacing.md,
    paddingVertical: 12,
  },
  copy: { flex: 1, gap: 2 },
  title: { fontFamily: fonts.bodyMedium, fontSize: 14, fontWeight: '700' },
  body: { flex: 1, fontFamily: fonts.body, fontSize: 13, lineHeight: 18 },
});
