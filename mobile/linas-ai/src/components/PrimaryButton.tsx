import type { ReactNode } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, type ViewStyle } from 'react-native';

import { colors, fonts, radii, spacing } from '../theme';

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
  const isPrimary = variant === 'primary';
  const isDanger = variant === 'danger';
  return (
    <Pressable
      style={[
        styles.base,
        isPrimary && styles.primary,
        variant === 'ghost' && styles.ghost,
        isDanger && styles.danger,
        (disabled || loading) && styles.disabled,
        style,
      ]}
      onPress={onPress}
      disabled={disabled || loading}
    >
      {loading ? (
        <ActivityIndicator color={isPrimary ? colors.bg : colors.accent} />
      ) : (
        <>
          {icon}
          <Text
            style={[
              styles.label,
              isPrimary && styles.labelOnPrimary,
              variant === 'ghost' && styles.labelGhost,
              isDanger && styles.labelDanger,
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
  primary: { backgroundColor: colors.accent },
  ghost: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
  },
  danger: {
    backgroundColor: 'transparent',
    borderWidth: 1,
    borderColor: colors.danger,
  },
  disabled: { opacity: 0.5 },
  label: { fontFamily: fonts.bodyMedium, fontSize: 16 },
  labelOnPrimary: { color: colors.bg, fontWeight: '700' },
  labelGhost: { color: colors.text },
  labelDanger: { color: colors.danger, fontWeight: '700' },
});
