import { useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { z } from 'zod';

import { apiFetch, ApiError } from '../../api/client';
import { colors } from '../../theme/colors';

const RegisterSchema = z.object({
  success: z.boolean(),
  error: z.string().optional(),
});

type Props = {
  onBack: () => void;
};

export function RegisterScreen({ onBack }: Props) {
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
      setMessage(result.success ? 'Registered. Verify your email, then sign in.' : result.error ?? 'Failed');
    } catch (err) {
      setMessage(err instanceof ApiError ? 'Registration failed' : 'Network error');
    } finally {
      setLoading(false);
    }
  }

  return (
    <View style={styles.root}>
      <Pressable onPress={onBack}>
        <Text style={styles.link}>Back</Text>
      </Pressable>
      <Text style={styles.title}>Create Linas AI account</Text>
      <TextInput style={styles.input} placeholder="Business name" placeholderTextColor={colors.textMuted} value={businessName} onChangeText={setBusinessName} />
      <TextInput style={styles.input} autoCapitalize="none" keyboardType="email-address" placeholder="Email" placeholderTextColor={colors.textMuted} value={email} onChangeText={setEmail} />
      <TextInput style={styles.input} secureTextEntry placeholder="Password" placeholderTextColor={colors.textMuted} value={password} onChangeText={setPassword} />
      {message ? <Text style={styles.msg}>{message}</Text> : null}
      <Pressable style={styles.button} onPress={onSubmit} disabled={loading}>
        {loading ? <ActivityIndicator color={colors.bg} /> : <Text style={styles.buttonText}>Register</Text>}
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg, padding: 24, justifyContent: 'center' },
  title: { color: colors.text, fontSize: 28, fontWeight: '700', marginVertical: 16 },
  input: { backgroundColor: colors.input, borderColor: colors.border, borderWidth: 1, borderRadius: 12, color: colors.text, padding: 14, marginBottom: 12 },
  button: { backgroundColor: colors.accent, borderRadius: 12, padding: 14, alignItems: 'center' },
  buttonText: { color: colors.bg, fontWeight: '700' },
  link: { color: colors.accent },
  msg: { color: colors.textMuted, marginBottom: 12 },
});
