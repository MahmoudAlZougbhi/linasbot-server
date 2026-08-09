import { Pressable, StyleSheet, Text, View } from 'react-native';

import { colors, fonts, radii, spacing } from '../../../theme';
import type { StreamChoice } from './useOwnerStream';

type Props = {
  choices: StreamChoice[];
  disabled?: boolean;
  onSelect: (choice: StreamChoice) => void;
};

/** Max three primary choices — backend-authoritative. */
export function ChoiceChips({ choices, disabled, onSelect }: Props) {
  const items = choices.slice(0, 3);
  if (!items.length) return null;
  return (
    <View style={styles.wrap} accessibilityRole="radiogroup">
      {items.map((c) => (
        <Pressable
          key={c.id}
          style={[styles.chip, disabled && styles.disabled]}
          disabled={disabled}
          accessibilityRole="button"
          accessibilityLabel={c.label}
          onPress={() => onSelect(c)}
        >
          <Text style={styles.label}>{c.label}</Text>
        </Pressable>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, paddingHorizontal: spacing.md, marginBottom: spacing.sm },
  chip: {
    backgroundColor: colors.bgElevated,
    borderColor: colors.accent,
    borderWidth: 1,
    borderRadius: radii.md,
    paddingVertical: 10,
    paddingHorizontal: 14,
    maxWidth: '100%',
  },
  disabled: { opacity: 0.5 },
  label: { color: colors.text, fontFamily: fonts.bodyMedium, fontSize: 14 },
});
