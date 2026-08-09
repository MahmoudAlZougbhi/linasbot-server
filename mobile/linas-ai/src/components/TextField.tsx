import { StyleSheet, TextInput, type TextInputProps } from 'react-native';

import { colors, fonts, radii, spacing } from '../theme';

type Props = TextInputProps;

export function TextField(props: Props) {
  return (
    <TextInput
      placeholderTextColor={colors.textDim}
      {...props}
      style={[styles.input, props.multiline && styles.multi, props.style]}
    />
  );
}

const styles = StyleSheet.create({
  input: {
    backgroundColor: colors.input,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: radii.md,
    color: colors.text,
    fontFamily: fonts.body,
    fontSize: 16,
    paddingHorizontal: spacing.lg - 2,
    paddingVertical: spacing.md + 2,
    marginBottom: spacing.md,
  },
  multi: { minHeight: 96, textAlignVertical: 'top' },
});
