import { Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { useEffect } from 'react';

import { AppIcon, ion } from '../../components/AppIcon';
import { useI18n } from '../../i18n/LanguageContext';
import { colors, fonts } from '../../theme';
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
  showDivider?: boolean;
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
      style={styles.circle}
      onPress={() => void onGoogle()}
      accessibilityRole="button"
      accessibilityLabel={tr('socialContinueGoogle')}
    >
      <AppIcon icon={ion('logo-google')} size={22} color="#4285F4" />
    </Pressable>
  );
}

/** Circular Google + Apple — Google stays live when client IDs are configured. */
export function SocialAuthButtons({
  onAppleSuccess,
  onAppleError,
  onGoogleSuccess,
  onGoogleError,
  showDivider = true,
}: Props) {
  const { tr } = useI18n();
  const appleEnabled = Platform.OS === 'ios';
  const googleEnabled = isGoogleSignInConfigured();

  async function onApple() {
    if (!appleEnabled) {
      onAppleError?.(tr('appleSignInUnavailable'));
      return;
    }
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
      {showDivider ? (
        <View style={styles.dividerRow}>
          <View style={styles.line} />
          <Text style={styles.or}>{tr('socialContinueWith')}</Text>
          <View style={styles.line} />
        </View>
      ) : null}
      <View style={styles.row}>
        {googleEnabled ? (
          <GoogleAuthButton onGoogleSuccess={onGoogleSuccess} onGoogleError={onGoogleError} />
        ) : (
          <Pressable
            style={styles.circle}
            onPress={() => onGoogleError?.(tr('googleSignInUnavailable'))}
            accessibilityRole="button"
            accessibilityLabel={tr('socialContinueGoogle')}
          >
            <AppIcon icon={ion('logo-google')} size={22} color="#4285F4" />
          </Pressable>
        )}
        <Pressable
          style={styles.circle}
          onPress={() => void onApple()}
          accessibilityRole="button"
          accessibilityLabel={tr('socialContinueApple')}
        >
          <AppIcon icon={ion('logo-apple')} size={24} color={colors.text} />
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { marginTop: 8, alignItems: 'center' },
  dividerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    marginBottom: 20,
    alignSelf: 'stretch',
  },
  line: { flex: 1, height: StyleSheet.hairlineWidth, backgroundColor: colors.border },
  or: { color: colors.textDim, fontFamily: fonts.body, fontSize: 14 },
  row: { flexDirection: 'row', justifyContent: 'center', gap: 20 },
  circle: {
    width: 56,
    height: 56,
    borderRadius: 28,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
