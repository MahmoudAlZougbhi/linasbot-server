import { Pressable, StyleSheet, Text, View } from 'react-native';

import { useI18n } from '../../i18n/LanguageContext';
import { fonts, radii, spacing, useTheme } from '../../theme';

type Props = {
  active: boolean;
  onClear?: () => void;
};

/** Multitask-style Edit chip above the composer while revising a proposal bar. */
export function ComposerEditChip({ active, onClear }: Props) {
  const { colors } = useTheme();
  const { tr } = useI18n();
  if (!active) return null;
  return (
    <View style={styles.editChipRow}>
      <View style={[styles.editChip, { backgroundColor: colors.accentSoft, borderColor: colors.accent }]}>
        <Text style={[styles.editChipText, { color: colors.accentDeep }]}>{tr('proposalEditChip')}</Text>
        <Pressable onPress={onClear} hitSlop={8} accessibilityLabel={tr('proposalEditChipClear')}>
          <Text style={{ color: colors.accentDeep, fontFamily: fonts.bodyMedium }}>✕</Text>
        </Pressable>
      </View>
      <Text style={[styles.editHint, { color: colors.textDim }]} numberOfLines={1}>
        {tr('proposalEditHint')}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  editChipRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: spacing.sm,
    paddingHorizontal: 2,
  },
  editChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radii.pill,
    paddingHorizontal: 10,
    paddingVertical: 4,
  },
  editChipText: { fontFamily: fonts.bodyMedium, fontSize: 12 },
  editHint: { flex: 1, fontFamily: fonts.body, fontSize: 12 },
});
