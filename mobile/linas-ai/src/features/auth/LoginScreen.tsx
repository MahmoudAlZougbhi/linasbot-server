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
import { colors, fonts, spacing, typography } from '../../theme';
import { SocialAuthButtons } from './SocialAuthButtons';

type Props = {
  onLoggedIn: () => void;
  onGoRegister: () => void;
  onBack?: () => void;
};

export function LoginScreen({ onLoggedIn, onGoRegister, onBack }: Props) {
  const insets = useSafeAreaInsets();
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
            ? 'Login failed. Check your email and password.'
            : 'Linas API is not ready for mobile login yet. Try again after the beta backend is live.',
        );
      } else {
        setError('Unable to reach Linas AI. Check your network and try again.');
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
              <Text style={styles.back}>← Continue as guest</Text>
            </Pressable>
          ) : null}
          <BrandMark size="lg" style={styles.hero} />
          <Text style={styles.welcome}>Welcome to Linas AI</Text>
          <Text style={styles.sub}>Think it. Ask it. Linas has it.</Text>

          <TextField
            autoCapitalize="none"
            keyboardType="email-address"
            autoComplete="email"
            placeholder="Email"
            value={email}
            onChangeText={setEmail}
          />
          <TextField
            secureTextEntry
            autoComplete="password"
            placeholder="Password"
            value={password}
            onChangeText={setPassword}
          />
          {error ? <Text style={styles.error}>{error}</Text> : null}

          <PrimaryButton label="Log in" onPress={() => void onSubmit()} loading={loading} />
          <PrimaryButton label="Create Account" onPress={onGoRegister} variant="ghost" />

          <Pressable onPress={() => void Linking.openURL(LEGAL_URLS.forgotPassword)}>
            <Text style={styles.link}>Forgot password</Text>
          </Pressable>

          <SocialAuthButtons />
          <View style={styles.legal}>
            <Text style={styles.legalText}>
              By continuing you agree to our Terms of Service and Privacy Policy.
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
});
