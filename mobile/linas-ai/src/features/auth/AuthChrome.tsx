import type { ReactNode } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { AppIcon, feather } from '../../components/AppIcon';
import { LinasSparkleIcon } from '../../components/LinasSparkleIcon';
import { useI18n } from '../../i18n/LanguageContext';
import { colors, fonts, spacing, typography } from '../../theme';
import { AuthProgressBar } from './AuthProgressBar';

type Props = {
  onBack?: () => void;
  progress?: 1 | 2 | 3;
  stepLabel?: string;
  title: string;
  subtitle?: string;
  sparkleSize?: number;
  children: ReactNode;
  footer?: ReactNode;
};

export function AuthChrome({
  onBack,
  progress,
  stepLabel,
  title,
  subtitle,
  sparkleSize = 48,
  children,
  footer,
}: Props) {
  const insets = useSafeAreaInsets();
  const { tr } = useI18n();

  return (
    <View style={styles.root}>
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <ScrollView
          contentContainerStyle={[
            styles.content,
            { paddingTop: insets.top + 12, paddingBottom: insets.bottom + 24 },
          ]}
          keyboardShouldPersistTaps="handled"
        >
          <View style={styles.header}>
            {onBack ? (
              <Pressable
                onPress={onBack}
                hitSlop={12}
                style={styles.backBtn}
                accessibilityRole="button"
                accessibilityLabel={tr('back')}
              >
                <AppIcon icon={feather('chevron-left')} size={28} color={colors.text} />
              </Pressable>
            ) : (
              <View style={styles.backBtn} />
            )}
            <View style={styles.sparkle}>
              <LinasSparkleIcon size={sparkleSize} color={colors.accent} />
            </View>
            <View style={styles.backBtn} />
          </View>
          {progress ? <AuthProgressBar filled={progress} /> : null}
          {stepLabel ? <Text style={styles.step}>{stepLabel}</Text> : null}
          <Text style={styles.title}>{title}</Text>
          {subtitle ? <Text style={styles.sub}>{subtitle}</Text> : null}
          {children}
          {footer ? <View style={styles.footer}>{footer}</View> : null}
        </ScrollView>
      </KeyboardAvoidingView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  flex: { flex: 1 },
  content: { paddingHorizontal: spacing.xl, flexGrow: 1 },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    minHeight: 48,
  },
  backBtn: { width: 40, height: 40, justifyContent: 'center' },
  sparkle: { flex: 1, alignItems: 'center' },
  step: {
    color: colors.textDim,
    fontFamily: fonts.body,
    fontSize: 13,
    textAlign: 'center',
    marginBottom: spacing.md,
  },
  title: {
    ...typography.title,
    color: colors.text,
    fontSize: 28,
    textAlign: 'center',
    marginTop: spacing.sm,
  },
  sub: {
    ...typography.subtitle,
    color: colors.textMuted,
    textAlign: 'center',
    marginTop: 8,
    marginBottom: spacing.xl,
  },
  footer: { marginTop: 'auto', paddingTop: spacing.xl, alignItems: 'center' },
});
