import type { ReactNode } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { GradientBackground } from '../../components/GradientBackground';
import { colors, fonts, spacing, typography } from '../../theme';

type Props = {
  title: string;
  subtitle?: string;
  onBack: () => void;
  children: ReactNode;
};

export function ScreenChrome({ title, subtitle, onBack, children }: Props) {
  const insets = useSafeAreaInsets();
  return (
    <GradientBackground>
      <View style={[styles.top, { paddingTop: insets.top + 8 }]}>
        <Pressable onPress={onBack}>
          <Text style={styles.back}>← Back to chat</Text>
        </Pressable>
        <Text style={styles.title}>{title}</Text>
        {subtitle ? <Text style={styles.sub}>{subtitle}</Text> : null}
      </View>
      <View style={styles.body}>{children}</View>
    </GradientBackground>
  );
}

const styles = StyleSheet.create({
  top: { paddingHorizontal: spacing.lg, paddingBottom: spacing.md },
  back: { color: colors.accent, fontFamily: fonts.bodyMedium, marginBottom: 8 },
  title: { ...typography.title, color: colors.text },
  sub: { color: colors.textMuted, fontFamily: fonts.body, marginTop: 4, fontSize: 14 },
  body: { flex: 1, paddingHorizontal: spacing.lg },
});
