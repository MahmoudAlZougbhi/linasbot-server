import type { ReactNode } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { GradientBackground } from '../../components/GradientBackground';
import { fonts, spacing, typography, useTheme } from '../../theme';

type Props = {
  title: string;
  subtitle?: string;
  onBack: () => void;
  backLabel?: string;
  children: ReactNode;
};

export function ScreenChrome({ title, subtitle, onBack, backLabel, children }: Props) {
  const insets = useSafeAreaInsets();
  const { colors } = useTheme();
  return (
    <GradientBackground>
      <View style={[styles.top, { paddingTop: insets.top + 8 }]}>
        <Pressable onPress={onBack} accessibilityLabel={backLabel ?? 'Back to chat'} hitSlop={8}>
          <Text style={{ color: colors.accent, fontFamily: fonts.bodyMedium, marginBottom: 8 }}>
            {backLabel ?? '← Back to chat'}
          </Text>
        </Pressable>
        <Text style={[typography.title, { color: colors.text }]}>{title}</Text>
        {subtitle ? (
          <Text style={{ color: colors.textMuted, fontFamily: fonts.body, marginTop: 4, fontSize: 14 }}>
            {subtitle}
          </Text>
        ) : null}
      </View>
      <View style={styles.body}>{children}</View>
    </GradientBackground>
  );
}

const styles = StyleSheet.create({
  top: { paddingHorizontal: spacing.lg, paddingBottom: spacing.md },
  body: { flex: 1, paddingHorizontal: spacing.lg },
});
