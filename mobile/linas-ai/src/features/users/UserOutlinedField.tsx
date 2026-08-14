import { StyleSheet, Text, TextInput, View, type TextInputProps } from 'react-native';

import { colors, fonts, radii, spacing } from '../../theme';

type Props = TextInputProps & {
  label: string;
};

export function UserOutlinedField({ label, style, ...rest }: Props) {
  return (
    <View style={styles.wrap}>
      <View style={styles.labelHit}>
        <Text style={styles.label}>{label}</Text>
      </View>
      <TextInput
        placeholderTextColor={colors.textDim}
        {...rest}
        style={[styles.input, style]}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { marginTop: 10 },
  labelHit: {
    position: 'absolute',
    top: -8,
    left: 12,
    zIndex: 2,
    backgroundColor: colors.surface,
    paddingHorizontal: 6,
  },
  label: { fontFamily: fonts.body, fontSize: 12, color: colors.textMuted },
  input: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.md,
    fontFamily: fonts.body,
    fontSize: 16,
    color: colors.text,
    paddingHorizontal: spacing.lg - 2,
    paddingVertical: 14,
  },
});
