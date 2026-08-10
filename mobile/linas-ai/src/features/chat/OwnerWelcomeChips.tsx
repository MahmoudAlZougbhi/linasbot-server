import { Pressable, StyleSheet, Text, View } from 'react-native';

import { fonts, radii, spacing, useTheme } from '../../theme';
import { OWNER_WELCOME_CHIPS, type OwnerWelcomeChip } from './ownerWelcomeChips';

type Props = {
  disabled?: boolean;
  onPick: (chip: OwnerWelcomeChip) => void;
};

/** Tappable questions under the seeded owner welcome message. */
export function OwnerWelcomeChips({ disabled, onPick }: Props) {
  const { colors } = useTheme();
  return (
    <View style={styles.wrap} accessibilityRole="menu">
      <Text style={[styles.hint, { color: colors.textDim }]}>Quick start</Text>
      {OWNER_WELCOME_CHIPS.map((chip) => (
        <Pressable
          key={chip.id}
          disabled={disabled}
          accessibilityRole="button"
          accessibilityLabel={chip.label}
          onPress={() => onPick(chip)}
          style={[
            styles.chip,
            {
              backgroundColor: colors.surface,
              borderColor: colors.border,
              opacity: disabled ? 0.5 : 1,
            },
          ]}
        >
          <Text style={[styles.label, { color: colors.text }]}>{chip.label}</Text>
          <Text style={{ color: colors.textDim }}>{chip.mode === 'work' ? 'Work · High' : 'Chat · Low'}</Text>
        </Pressable>
      ))}
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
