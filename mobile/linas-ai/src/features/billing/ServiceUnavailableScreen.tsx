import { Pressable, StyleSheet, Text, View } from 'react-native';

import { GradientBackground } from '../../components/GradientBackground';
import { LinasLoadingIndicator } from '../../components/LinasLoadingIndicator';
import { LinasStarMark } from '../../components/LinasStarMark';
import { useI18n } from '../../i18n/LanguageContext';
import { fonts, radii, spacing, useTheme } from '../../theme';

type Props = {
  loading?: boolean;
  onRetry: () => void;
  onLogout: () => void;
};

/** Blocks the app while the API is down (deploy drain, 502) instead of a subscribe wall. */
export function ServiceUnavailableScreen({ loading, onRetry, onLogout }: Props) {
  const { colors } = useTheme();
  const { tr } = useI18n();
  return (
    <GradientBackground>
      <View style={styles.wrap}>
        <LinasStarMark size={48} />
        <Text style={[styles.title, { color: colors.text }]}>{tr('serviceUnavailableTitle')}</Text>
        <Text style={[styles.body, { color: colors.textMuted }]}>{tr('serviceUnavailableBody')}</Text>
        {loading ? <LinasLoadingIndicator variant="inline" /> : null}
        <Pressable
          style={[styles.btn, { backgroundColor: colors.accent }]}
          onPress={onRetry}
          accessibilityRole="button"
          accessibilityLabel={tr('serviceUnavailableRetry')}
        >
          <Text style={styles.btnText}>{tr('serviceUnavailableRetry')}</Text>
        </Pressable>
        <Pressable onPress={onLogout} accessibilityRole="button">
          <Text style={{ color: colors.textDim, marginTop: spacing.md }}>
            {tr('subscribeGateSignOut')}
          </Text>
        </Pressable>
      </View>
    </GradientBackground>
  );
}

const styles = StyleSheet.create({
  wrap: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.xl,
    gap: spacing.md,
  },
  title: { fontFamily: fonts.display, fontSize: 24, textAlign: 'center', marginTop: spacing.md },
  body: { fontFamily: fonts.body, fontSize: 14, textAlign: 'center', maxWidth: 340 },
  btn: {
    marginTop: spacing.md,
    minHeight: 48,
    borderRadius: radii.md,
    paddingHorizontal: 28,
    alignItems: 'center',
    justifyContent: 'center',
    alignSelf: 'stretch',
  },
  btnText: { color: '#fff', fontFamily: fonts.bodyMedium, fontSize: 16 },
});
