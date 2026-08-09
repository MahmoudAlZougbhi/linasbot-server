import { useState } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { z } from 'zod';

import { apiFetch, ApiError } from '../../api/client';
import { BrandMark } from '../../components/BrandMark';
import { GradientBackground } from '../../components/GradientBackground';
import { PrimaryButton } from '../../components/PrimaryButton';
import { TextField } from '../../components/TextField';
import { colors, fonts, spacing, typography } from '../../theme';
import { SocialAuthButtons } from './SocialAuthButtons';

const RegisterSchema = z.object({
  success: z.boolean(),
  error: z.string().optional(),
});

type Props = {
  onBack: () => void;
};

export function RegisterScreen({ onBack }: Props) {
  const insets = useSafeAreaInsets();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [businessName, setBusinessName] = useState('');
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit() {
    setLoading(true);
    setMessage(null);
    try {
      const result = await apiFetch('/api/auth/register', {
        method: 'POST',
        auth: false,
        body: JSON.stringify({
          email: email.trim(),
          password,
          business_name: businessName.trim(),
        }),
        schema: RegisterSchema,
      });
      setMessage(
        result.success
          ? 'Registered. Verify your email, then log in.'
          : (result.error ?? 'Registration failed'),
      );
    } catch (err) {
      setMessage(err instanceof ApiError ? 'Registration failed' : 'Network error');
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
          <Pressable onPress={onBack}>
            <Text style={styles.back}>← Back to log in</Text>
          </Pressable>
          <BrandMark size="md" showWordmark />
          <Text style={styles.title}>Create account</Text>
          <Text style={styles.sub}>Start your business AI workspace</Text>

          <TextField
            placeholder="Business name"
            value={businessName}
            onChangeText={setBusinessName}
          />
          <TextField
            autoCapitalize="none"
            keyboardType="email-address"
            placeholder="Email"
            value={email}
            onChangeText={setEmail}
          />
          <TextField
            secureTextEntry
            placeholder="Password"
            value={password}
            onChangeText={setPassword}
          />
          {message ? <Text style={styles.msg}>{message}</Text> : null}
          <PrimaryButton label="Create account" onPress={() => void onSubmit()} loading={loading} />
          <SocialAuthButtons />
        </ScrollView>
      </KeyboardAvoidingView>
    </GradientBackground>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  content: { paddingHorizontal: spacing.xl, flexGrow: 1 },
  back: { color: colors.accent, fontFamily: fonts.bodyMedium, marginBottom: spacing.lg },
  title: { ...typography.title, color: colors.text, marginTop: spacing.lg },
  sub: { ...typography.subtitle, color: colors.textMuted, marginBottom: spacing.xl, marginTop: 6 },
  msg: { color: colors.textMuted, fontFamily: fonts.body, marginBottom: spacing.md },
});
