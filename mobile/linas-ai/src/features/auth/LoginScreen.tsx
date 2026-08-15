import { useState } from 'react';
import { Linking, Pressable, StyleSheet, Text, View } from 'react-native';

import { ApiError, mobileLogin } from '../../api/client';
import { PrimaryButton } from '../../components/PrimaryButton';
import { LEGAL_URLS } from '../../config';
import { useI18n } from '../../i18n/LanguageContext';
import { colors, fonts, spacing } from '../../theme';
import { AuthChrome } from './AuthChrome';
import { AuthPasswordField, AuthTextField } from './AuthFields';
import { SocialAuthButtons } from './SocialAuthButtons';

type Props = {
  onLoggedIn: () => void;
  onGoRegister: () => void;
  onForgotPassword: () => void;
  onBack?: () => void;
};

export function LoginScreen({ onLoggedIn, onGoRegister, onForgotPassword, onBack }: Props) {
  const { tr } = useI18n();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit() {
    setLoading(true);
    setError(null);
    try {
      await mobileLogin(email.trim(), password);
      onLoggedIn();
    } catch (err) {
      if (err instanceof ApiError) {
        setError(
          err.status === 401 || err.status === 403 ? tr('loginFailed') : tr('loginGenericError'),
        );
      } else {
        setError(tr('loginNetworkError'));
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthChrome title={tr('loginWelcome')} subtitle={tr('loginTagline')} sparkleSize={52}>
      <AuthTextField
        autoCapitalize="none"
        keyboardType="email-address"
        autoComplete="email"
        placeholder={tr('email')}
        value={email}
        onChangeText={setEmail}
      />
      <AuthPasswordField
        autoComplete="password"
        placeholder={tr('password')}
        value={password}
        onChangeText={setPassword}
      />
      <Pressable onPress={onForgotPassword} style={styles.forgot}>
        <Text style={styles.forgotText}>{tr('forgotPassword')}</Text>
      </Pressable>
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <PrimaryButton label={tr('login')} onPress={() => void onSubmit()} loading={loading} />
      <Text style={styles.switchRow}>
        <Text style={styles.muted}>{tr('newToLinas')} </Text>
        <Text style={styles.link} onPress={onGoRegister}>
          {tr('createAccount')}
        </Text>
      </Text>
      <SocialAuthButtons
        onAppleSuccess={onLoggedIn}
        onAppleError={setError}
        onGoogleSuccess={onLoggedIn}
        onGoogleError={setError}
      />
      {onBack ? (
        <Pressable onPress={onBack} style={styles.guest}>
          <Text style={styles.link}>{tr('continueAsGuestShort')}</Text>
        </Pressable>
      ) : null}
      <View style={styles.legal}>
        <Text style={styles.legalLink} onPress={() => void Linking.openURL(LEGAL_URLS.terms)}>
          {tr('terms')}
        </Text>
        <Text style={styles.legalDot}> • </Text>
        <Text style={styles.legalLink} onPress={() => void Linking.openURL(LEGAL_URLS.privacy)}>
          {tr('privacy')}
        </Text>
      </View>
    </AuthChrome>
  );
}

const styles = StyleSheet.create({
  forgot: { alignSelf: 'flex-end', marginTop: -4, marginBottom: spacing.lg },
  forgotText: { color: colors.accent, fontFamily: fonts.body, fontSize: 14 },
  error: { color: colors.danger, fontFamily: fonts.body, marginBottom: spacing.sm },
  switchRow: { textAlign: 'center', marginTop: spacing.lg, marginBottom: spacing.md, fontSize: 15 },
  muted: { color: colors.text, fontFamily: fonts.body },
  link: { color: colors.accent, fontFamily: fonts.bodyMedium },
  guest: { alignItems: 'center', marginTop: spacing.xl },
  legal: {
    flexDirection: 'row',
    justifyContent: 'center',
    marginTop: spacing.xl,
    paddingBottom: spacing.sm,
  },
  legalLink: { color: colors.textDim, fontFamily: fonts.body, fontSize: 13 },
  legalDot: { color: colors.textDim, fontSize: 13 },
});
