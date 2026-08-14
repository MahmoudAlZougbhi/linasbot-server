import { Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { useEffect } from 'react';

import { StatusChip } from '../../components/StatusChip';
import { useI18n } from '../../i18n/LanguageContext';
import { colors, fonts, radii, spacing } from '../../theme';
import { signInWithApple } from './appleSignIn';
import {
  completeGoogleSignIn,
  isGoogleSignInConfigured,
  useGoogleIdTokenAuthRequest,
} from './googleSignIn';

type Props = {
  onAppleSuccess?: () => void;
  onAppleError?: (message: string) => void;
  onGoogleSuccess?: () => void;
  onGoogleError?: (message: string) => void;
};

function GoogleAuthButton({
  onGoogleSuccess,
  onGoogleError,
}: Pick<Props, 'onGoogleSuccess' | 'onGoogleError'>) {
  const { tr } = useI18n();
  const [googleRequest, googleResponse, promptGoogle] = useGoogleIdTokenAuthRequest();

  useEffect(() => {
    if (!googleResponse) return;
    if (googleResponse.type === 'dismiss' || googleResponse.type === 'cancel') return;
    if (googleResponse.type !== 'success') {
      onGoogleError?.(tr('googleSignInFailed'));
      return;
    }
    const idToken =
      googleResponse.params.id_token ||
      (googleResponse.authentication as { idToken?: string } | null)?.idToken;
    void (async () => {
      const result = await completeGoogleSignIn({ idToken: String(idToken || '') });
      if (result.ok) {
        onGoogleSuccess?.();
        return;
      }
      if (result.code === 'link_required') {
        onGoogleError?.(tr('googleLinkRequired'));
        return;
      }
      onGoogleError?.(tr('googleSignInFailed'));
    })();
  }, [googleResponse, onGoogleError, onGoogleSuccess, tr]);

  async function onGoogle() {
    if (!googleRequest) {
      onGoogleError?.(tr('googleSignInUnavailable'));
      return;
    }
    try {
      await promptGoogle();
    } catch {
      onGoogleError?.(tr('googleSignInFailed'));
    }
  }

  return (
    <Pressable
      style={[styles.btn, styles.btnEnabled]}
      onPress={() => void onGoogle()}
      accessibilityRole="button"
      accessibilityLabel={tr('socialContinueGoogle')}
    >
      <Text style={styles.btnTextActive}>{tr('socialContinueGoogle')}</Text>
    </Pressable>
  );
}

/** Google Sign-In (when client IDs configured) + Apple Sign In (iOS). */
export function SocialAuthButtons({
  onAppleSuccess,
  onAppleError,
  onGoogleSuccess,
  onGoogleError,
}: Props) {
  const { tr } = useI18n();
  const appleEnabled = Platform.OS === 'ios';
  const googleEnabled = isGoogleSignInConfigured();

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
      {googleEnabled ? (
        <GoogleAuthButton onGoogleSuccess={onGoogleSuccess} onGoogleError={onGoogleError} />
      ) : (
        <Pressable style={styles.btn} disabled>
          <Text style={styles.btnText}>{tr('socialContinueGoogle')}</Text>
          <StatusChip label={tr('comingSoon')} tone="soon" />
        </Pressable>
      )}
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
