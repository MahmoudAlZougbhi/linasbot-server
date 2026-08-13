import { useState } from 'react';
import {
  KeyboardAvoidingView,
  Linking,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { ApiError, mobileLogin } from '../../api/client';
import { BrandMark } from '../../components/BrandMark';
import { GradientBackground } from '../../components/GradientBackground';
import { PrimaryButton } from '../../components/PrimaryButton';
import { TextField } from '../../components/TextField';
import { LEGAL_URLS } from '../../config';
import { useI18n } from '../../i18n/LanguageContext';
import { colors, fonts, spacing, typography } from '../../theme';
import { SocialAuthButtons } from './SocialAuthButtons';

type Props = {
  onLoggedIn: () => void;
  onGoRegister: () => void;
  onBack?: () => void;
};

export function LoginScreen({ onLoggedIn, onGoRegister, onBack }: Props) {
  const insets = useSafeAreaInsets();
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
          err.status === 401 || err.status === 403
            ? tr('loginFailed')
            : tr('loginGenericError'),
        );
      } else {
        setError(tr('loginNetworkError'));
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <GradientBackground>
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <ScrollView
          contentContainerStyle={[
            styles.content,
            { paddingTop: insets.top + 24, paddingBottom: insets.bottom + 24 },
          ]}
          keyboardShouldPersistTaps="handled"
        >
          {onBack ? (
            <Pressable onPress={onBack}>
              <Text style={styles.back}>{tr('continueAsGuestBack')}</Text>
            </Pressable>
          ) : null}
          <BrandMark size="lg" style={styles.hero} />
          <Text style={styles.welcome}>{tr('loginWelcome')}</Text>
          <Text style={styles.sub}>{tr('loginTagline')}</Text>

          <TextField
            autoCapitalize="none"
            keyboardType="email-address"
            autoComplete="email"
            placeholder={tr('email')}
            value={email}
            onChangeText={setEmail}
          />
          <TextField
            secureTextEntry
            autoComplete="password"
            placeholder={tr('password')}
            value={password}
            onChangeText={setPassword}
          />
          {error ? <Text style={styles.error}>{error}</Text> : null}

          <PrimaryButton label={tr('login')} onPress={() => void onSubmit()} loading={loading} />
          <PrimaryButton label={tr('createAccount')} onPress={onGoRegister} variant="ghost" />

          <Pressable onPress={() => void Linking.openURL(LEGAL_URLS.forgotPassword)}>
            <Text style={styles.link}>{tr('forgotPassword')}</Text>
          </Pressable>

          <SocialAuthButtons
            onAppleSuccess={onLoggedIn}
            onAppleError={(message) => setError(message)}
            onGoogleSuccess={onLoggedIn}
            onGoogleError={(message) => setError(message)}
          />
          <View style={styles.legal}>
            <Text style={styles.legalText}>
              {tr('loginLegalAgree')}{' '}
              <Text style={styles.legalLink} onPress={() => void Linking.openURL(LEGAL_URLS.terms)}>
                {tr('terms')}
              </Text>
              {' · '}
              <Text style={styles.legalLink} onPress={() => void Linking.openURL(LEGAL_URLS.privacy)}>
                {tr('privacy')}
              </Text>
            </Text>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </GradientBackground>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  content: { paddingHorizontal: spacing.xl, justifyContent: 'center', flexGrow: 1 },
  back: { color: colors.accent, fontFamily: fonts.bodyMedium, marginBottom: spacing.md },
  welcome: {
    ...typography.title,
    color: colors.accentDeep,
    fontSize: 28,
    textAlign: 'center',
  },
  sub: {
    ...typography.subtitle,
    color: colors.textMuted,
    marginTop: spacing.sm,
    marginBottom: spacing.md,
    textAlign: 'center',
  },
  hero: { marginBottom: spacing.lg },
  error: { color: colors.danger, fontFamily: fonts.body, marginBottom: spacing.sm },
  link: { color: colors.accent, fontFamily: fonts.body, marginTop: spacing.lg, fontSize: 15 },
  legal: { marginTop: spacing.xl },
  legalText: { color: colors.textDim, fontFamily: fonts.body, fontSize: 12, lineHeight: 17 },
  legalLink: { color: colors.accent, fontFamily: fonts.bodyMedium, fontSize: 12 },
});
