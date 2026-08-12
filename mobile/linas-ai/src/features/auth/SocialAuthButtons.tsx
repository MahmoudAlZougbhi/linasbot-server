import { Platform, Pressable, StyleSheet, Text, View } from 'react-native';

import { StatusChip } from '../../components/StatusChip';
import { useI18n } from '../../i18n/LanguageContext';
import { colors, fonts, radii, spacing } from '../../theme';
import { signInWithApple } from './appleSignIn';

type Props = {
  onAppleSuccess?: () => void;
  onAppleError?: (message: string) => void;
};

/** Google (soon) + Apple Sign In (iOS). */
export function SocialAuthButtons({ onAppleSuccess, onAppleError }: Props) {
  const { tr } = useI18n();
  const appleEnabled = Platform.OS === 'ios';

  async function onApple() {
    const result = await signInWithApple();
    if (result.ok) {
      onAppleSuccess?.();
      return;
    }
    if (result.code === 'cancel') return;
    if (result.code === 'link_required') {
      onAppleError?.(tr('appleLinkRequired'));
      return;
    }
    if (result.code === 'unavailable') {
      onAppleError?.(tr('appleSignInUnavailable'));
      return;
    }
    onAppleError?.(tr('appleSignInFailed'));
  }

  return (
    <View style={styles.wrap}>
      <View style={styles.dividerRow}>
        <View style={styles.line} />
        <Text style={styles.or}>{tr('socialContinueWith')}</Text>
        <View style={styles.line} />
      </View>
      <Pressable style={styles.btn} disabled>
        <Text style={styles.btnText}>{tr('socialContinueGoogle')}</Text>
        <StatusChip label={tr('comingSoon')} tone="soon" />
      </Pressable>
      {appleEnabled ? (
        <Pressable
          style={[styles.btn, styles.btnEnabled]}
          onPress={() => void onApple()}
          accessibilityRole="button"
          accessibilityLabel={tr('socialContinueApple')}
        >
          <Text style={styles.btnTextActive}>{tr('socialContinueApple')}</Text>
        </Pressable>
      ) : (
        <Pressable style={styles.btn} disabled>
          <Text style={styles.btnText}>{tr('socialContinueApple')}</Text>
          <StatusChip label={tr('comingSoon')} tone="soon" />
        </Pressable>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { marginTop: spacing.xl, gap: spacing.sm },
  dividerRow: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: spacing.sm },
  line: { flex: 1, height: 1, backgroundColor: colors.border },
  or: { color: colors.textDim, fontFamily: fonts.body, fontSize: 12 },
  btn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: colors.surface,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md + 2,
    opacity: 0.72,
  },
  btnEnabled: { opacity: 1 },
  btnText: { color: colors.textMuted, fontFamily: fonts.bodyMedium, fontSize: 15 },
  btnTextActive: { color: colors.text, fontFamily: fonts.bodyMedium, fontSize: 15 },
});
