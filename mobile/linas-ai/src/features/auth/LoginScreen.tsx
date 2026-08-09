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
};

export function LoginScreen({ onLoggedIn, onGoRegister }: Props) {
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
            { paddingTop: insets.top + 36, paddingBottom: insets.bottom + 24 },
          ]}
          keyboardShouldPersistTaps="handled"
        >
          <BrandMark size="lg" showWordmark />
          <Text style={styles.sub}>Log in to operate your business AI</Text>

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

          <Pressable onPress={() => void Linking.openURL(LEGAL_URLS.forgotPassword)}>
            <Text style={styles.link}>Forgot password</Text>
          </Pressable>
          <Pressable onPress={onGoRegister}>
            <Text style={styles.linkStrong}>Create account</Text>
          </Pressable>

          <SocialAuthButtons />
          <View style={styles.legal}>
            <Text style={styles.legalText}>
              By continuing you agree to our Terms and Privacy Policy.
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
  sub: { ...typography.subtitle, color: colors.textMuted, marginTop: spacing.lg, marginBottom: spacing.xl },
  error: { color: colors.danger, fontFamily: fonts.body, marginBottom: spacing.sm },
  link: { color: colors.accent, fontFamily: fonts.body, marginTop: spacing.lg, fontSize: 15 },
  linkStrong: {
    color: colors.mint,
    fontFamily: fonts.bodyMedium,
    marginTop: spacing.md,
    fontSize: 15,
  },
  legal: { marginTop: spacing.xl },
  legalText: { color: colors.textDim, fontFamily: fonts.body, fontSize: 12, lineHeight: 17 },
});
