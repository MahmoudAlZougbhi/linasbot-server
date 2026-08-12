import { StyleSheet, TextInput, type TextInputProps } from 'react-native';

import { fonts, radii, spacing, useTheme } from '../theme';

type Props = TextInputProps;

export function TextField(props: Props) {
  const { colors } = useTheme();
  return (
    <TextInput
      placeholderTextColor={colors.textDim}
      {...props}
      style={[
        styles.input,
        {
          backgroundColor: colors.input,
          borderColor: colors.border,
          color: colors.text,
        },
        props.multiline && styles.multi,
        props.style,
      ]}
    />
  );
}

const styles = StyleSheet.create({
  input: {
    borderWidth: 1,
    borderRadius: radii.md,
    fontFamily: fonts.body,
    fontSize: 16,
    paddingHorizontal: spacing.lg - 2,
    paddingVertical: spacing.md + 2,
    marginBottom: spacing.md,
  },
  multi: { minHeight: 96, textAlignVertical: 'top' },
});
