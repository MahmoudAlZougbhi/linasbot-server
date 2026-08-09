import { useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import { ApiError, mobileLogin } from '../../api/client';
import { colors } from '../../theme/colors';

type Props = {
  onLoggedIn: () => void;
  onGoRegister: () => void;
  onGoForgot: () => void;
};

export function LoginScreen({ onLoggedIn, onGoRegister, onGoForgot }: Props) {
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
        setError('Login failed. Check your email and password.');
      } else {
        setError('Unable to reach Linas AI. Try again.');
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <View style={styles.root}>
      <Text style={styles.brand}>Linas AI</Text>
      <Text style={styles.sub}>Sign in to operate your business AI</Text>
      <TextInput
        style={styles.input}
        autoCapitalize="none"
        keyboardType="email-address"
        placeholder="Email"
        placeholderTextColor={colors.textMuted}
        value={email}
        onChangeText={setEmail}
      />
      <TextInput
        style={styles.input}
        secureTextEntry
        placeholder="Password"
        placeholderTextColor={colors.textMuted}
        value={password}
        onChangeText={setPassword}
      />
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <Pressable style={styles.button} onPress={onSubmit} disabled={loading}>
        {loading ? <ActivityIndicator color={colors.bg} /> : <Text style={styles.buttonText}>Sign in</Text>}
      </Pressable>
      <Pressable onPress={onGoForgot}>
        <Text style={styles.link}>Forgot password</Text>
      </Pressable>
      <Pressable onPress={onGoRegister}>
        <Text style={styles.link}>Create account</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg, padding: 24, justifyContent: 'center' },
  brand: { color: colors.text, fontSize: 40, fontWeight: '700', marginBottom: 8 },
  sub: { color: colors.textMuted, marginBottom: 28, fontSize: 16 },
  input: {
    backgroundColor: colors.input,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 12,
    color: colors.text,
    paddingHorizontal: 14,
    paddingVertical: 14,
    marginBottom: 12,
  },
  button: {
    backgroundColor: colors.accent,
    borderRadius: 12,
    paddingVertical: 14,
    alignItems: 'center',
    marginTop: 8,
    marginBottom: 16,
  },
  buttonText: { color: colors.bg, fontWeight: '700', fontSize: 16 },
  link: { color: colors.accent, marginTop: 10, fontSize: 15 },
  error: { color: colors.danger, marginBottom: 8 },
});
