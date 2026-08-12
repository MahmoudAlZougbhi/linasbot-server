import type { ReactNode } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, type ViewStyle } from 'react-native';

import { fonts, radii, spacing, useTheme } from '../theme';

type Props = {
  label: string;
  onPress: () => void;
  loading?: boolean;
  disabled?: boolean;
  variant?: 'primary' | 'ghost' | 'danger';
  style?: ViewStyle;
  icon?: ReactNode;
};

export function PrimaryButton({
  label,
  onPress,
  loading,
  disabled,
  variant = 'primary',
  style,
  icon,
}: Props) {
  const { colors } = useTheme();
  const isPrimary = variant === 'primary';
  const isDanger = variant === 'danger';
  return (
    <Pressable
      style={[
        styles.base,
        isPrimary && { backgroundColor: colors.accent },
        variant === 'ghost' && {
          backgroundColor: colors.surface,
          borderWidth: 1,
          borderColor: colors.border,
        },
        isDanger && {
          backgroundColor: 'transparent',
          borderWidth: 1,
          borderColor: colors.danger,
        },
        (disabled || loading) && styles.disabled,
        style,
      ]}
      onPress={onPress}
      disabled={disabled || loading}
    >
      {loading ? (
        <ActivityIndicator color={isPrimary ? colors.onAccent : colors.accent} />
      ) : (
        <>
          {icon}
          <Text
            style={[
              styles.label,
              isPrimary && { color: colors.onAccent, fontWeight: '700' },
              variant === 'ghost' && { color: colors.text },
              isDanger && { color: colors.danger, fontWeight: '700' },
            ]}
          >
            {label}
          </Text>
        </>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    borderRadius: radii.md,
    paddingVertical: spacing.md + 2,
    paddingHorizontal: spacing.lg,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: 8,
  },
  disabled: { opacity: 0.5 },
  label: { fontFamily: fonts.bodyMedium, fontSize: 16 },
});
