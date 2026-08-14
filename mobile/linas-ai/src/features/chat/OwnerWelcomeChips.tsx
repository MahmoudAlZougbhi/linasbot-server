import { Pressable, StyleSheet, Text, View } from 'react-native';

import { useI18n } from '../../i18n/LanguageContext';
import { fonts, radii, spacing, useTheme } from '../../theme';
import { OWNER_WELCOME_CHIPS } from './ownerWelcomeChipData';

export type OwnerWelcomeChip = {
  id: string;
  label: string;
  mode: 'chat' | 'work';
  prompt: string;
};

type Props = {
  disabled?: boolean;
  onPick: (chip: OwnerWelcomeChip) => void;
};

/** Tappable questions under the seeded owner welcome message. */
export function OwnerWelcomeChips({ disabled, onPick }: Props) {
  const { tr, isRtl } = useI18n();
  const { colors } = useTheme();
  const align = isRtl ? 'right' : 'left';
  return (
    <View style={styles.wrap} accessibilityRole="menu">
      <Text style={[styles.hint, { color: colors.textDim, textAlign: align }]}>{tr('welcomeQuickStart')}</Text>
      {OWNER_WELCOME_CHIPS.map((chip) => {
        const label = tr(chip.labelKey);
        return (
          <Pressable
            key={chip.id}
            disabled={disabled}
            accessibilityRole="button"
            accessibilityLabel={label}
            onPress={() => onPick({ id: chip.id, label, mode: chip.mode, prompt: chip.prompt })}
            style={[
              styles.chip,
              {
                backgroundColor: colors.surface,
                borderColor: colors.border,
                opacity: disabled ? 0.5 : 1,
              },
            ]}
          >
            <Text style={[styles.label, { color: colors.text, textAlign: align }]}>{label}</Text>
            <Text style={{ color: colors.textDim, textAlign: align }}>
              {chip.mode === 'work' ? tr('welcomeChipModeWork') : tr('welcomeChipModeChat')}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    width: '100%',
    gap: 8,
    paddingHorizontal: spacing.md,
    paddingBottom: spacing.sm,
    marginTop: 4,
  },
  hint: { fontFamily: fonts.body, fontSize: 12, marginBottom: 2, paddingHorizontal: 2 },
  chip: {
    borderWidth: 1,
    borderRadius: radii.md,
    paddingVertical: 12,
    paddingHorizontal: 14,
    gap: 4,
  },
  label: { fontFamily: fonts.bodyMedium, fontSize: 14 },
});
