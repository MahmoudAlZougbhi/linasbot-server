import { useState } from 'react';
import { Pressable, StyleSheet, TextInput, View, type TextInputProps } from 'react-native';

import { AppIcon, feather } from '../../components/AppIcon';
import { colors, fonts, radii, spacing } from '../../theme';

type FieldProps = TextInputProps;

export function AuthTextField(props: FieldProps) {
  return (
    <TextInput
      placeholderTextColor={colors.textDim}
      {...props}
      style={[styles.input, props.style]}
    />
  );
}

type PasswordProps = Omit<TextInputProps, 'secureTextEntry'> & {
  value: string;
  onChangeText: (next: string) => void;
};

export function AuthPasswordField({ value, onChangeText, ...rest }: PasswordProps) {
  const [visible, setVisible] = useState(false);
  return (
    <View style={styles.passwordWrap}>
      <TextInput
        placeholderTextColor={colors.textDim}
        secureTextEntry={!visible}
        autoCapitalize="none"
        autoCorrect={false}
        value={value}
        onChangeText={onChangeText}
        {...rest}
        style={styles.passwordInput}
      />
      <Pressable
        onPress={() => setVisible((v) => !v)}
        hitSlop={8}
        accessibilityRole="button"
        accessibilityLabel={visible ? 'Hide password' : 'Show password'}
        style={styles.eye}
      >
        <AppIcon icon={feather(visible ? 'eye-off' : 'eye')} size={20} color={colors.textDim} />
      </Pressable>
    </View>
  );
}

const fieldBorder = {
  borderWidth: 1,
  borderColor: colors.border,
  borderRadius: radii.md,
  backgroundColor: colors.surface,
} as const;

const styles = StyleSheet.create({
  input: {
    ...fieldBorder,
    fontFamily: fonts.body,
    fontSize: 16,
    color: colors.text,
    paddingHorizontal: spacing.lg - 2,
    paddingVertical: 14,
    marginBottom: spacing.md,
  },
  passwordWrap: {
    ...fieldBorder,
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: spacing.md,
  },
  passwordInput: {
    flex: 1,
    fontFamily: fonts.body,
    fontSize: 16,
    color: colors.text,
    paddingHorizontal: spacing.lg - 2,
    paddingVertical: 14,
  },
  eye: { paddingHorizontal: 12, paddingVertical: 10 },
});
