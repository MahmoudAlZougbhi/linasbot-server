import { useState } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { z } from 'zod';

import { apiFetch, ApiError } from '../../api/client';
import { BrandMark } from '../../components/BrandMark';
import { GradientBackground } from '../../components/GradientBackground';
import { PrimaryButton } from '../../components/PrimaryButton';
import { TextField } from '../../components/TextField';
import { useI18n } from '../../i18n/LanguageContext';
import { colors, fonts, spacing, typography } from '../../theme';
import { SocialAuthButtons } from './SocialAuthButtons';

const RegisterSchema = z.object({
  success: z.boolean(),
  error: z.string().optional(),
});

type Gender = 'unset' | 'male' | 'female';
type Step = 0 | 1 | 2 | 3;

type Props = {
  onBack: () => void;
  onDone?: () => void;
};

export function RegisterScreen({ onBack, onDone }: Props) {
  const insets = useSafeAreaInsets();
  const { tr, language } = useI18n();
  const [step, setStep] = useState<Step>(0);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [businessName, setBusinessName] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [gender, setGender] = useState<Gender>('unset');
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
          display_name: displayName.trim() || undefined,
          name: displayName.trim() || undefined,
          gender,
          preferred_language: language,
        }),
        schema: RegisterSchema,
      });
      if (result.success) {
        setStep(3);
        setMessage(tr('registeredVerify'));
      } else {
        setMessage(result.error ?? 'Registration failed');
      }
    } catch (err) {
      setMessage(err instanceof ApiError ? 'Registration failed' : 'Network error');
    } finally {
      setLoading(false);
    }
  }

  function nextFromCredentials() {
    if (!email.trim() || password.length < 6) {
      setMessage(tr('registerNeedCredentials'));
      return;
    }
    setMessage(null);
    setStep(1);
  }

  function nextFromName() {
    if (!businessName.trim()) {
      setMessage(tr('registerNeedBusiness'));
      return;
    }
    setMessage(null);
    setStep(2);
  }

  const stepLabel = `${tr('step')} ${Math.min(step + 1, 3)}/3`;

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
            <Text style={styles.back}>{tr('backToLogin')}</Text>
          </Pressable>
          <BrandMark size="md" showWordmark />
          <Text style={styles.title}>{tr('register')}</Text>
          {step < 3 ? <Text style={styles.step}>{stepLabel}</Text> : null}
          <Text style={styles.sub}>
            {step === 0
              ? tr('registerStepCredentials')
              : step === 1
                ? tr('registerStepName')
                : step === 2
                  ? tr('registerStepGender')
                  : tr('registeredVerify')}
          </Text>

          {step === 0 ? (
            <>
              <TextField
                autoCapitalize="none"
                keyboardType="email-address"
                placeholder={tr('email')}
                value={email}
                onChangeText={setEmail}
              />
              <TextField
                secureTextEntry
                placeholder={tr('password')}
                value={password}
                onChangeText={setPassword}
              />
              {message ? <Text style={styles.msg}>{message}</Text> : null}
              <PrimaryButton label={tr('continue')} onPress={nextFromCredentials} />
              <SocialAuthButtons />
            </>
          ) : null}

          {step === 1 ? (
            <>
              <TextField
                placeholder={tr('businessName')}
                value={businessName}
                onChangeText={setBusinessName}
              />
              <TextField
                placeholder={tr('displayName')}
                value={displayName}
                onChangeText={setDisplayName}
              />
              {message ? <Text style={styles.msg}>{message}</Text> : null}
              <PrimaryButton label={tr('continue')} onPress={nextFromName} />
              <PrimaryButton label={tr('back')} onPress={() => setStep(0)} variant="ghost" />
            </>
          ) : null}

          {step === 2 ? (
            <>
              <Text style={styles.label}>{tr('genderOptional')}</Text>
              <View style={styles.chips}>
                {(
                  [
                    ['unset', 'genderUnset'],
                    ['male', 'genderMale'],
                    ['female', 'genderFemale'],
                  ] as const
                ).map(([value, key]) => (
                  <Pressable
                    key={value}
                    style={[styles.chip, gender === value && styles.chipOn]}
                    onPress={() => setGender(value)}
                  >
                    <Text style={styles.chipText}>{tr(key)}</Text>
                  </Pressable>
                ))}
              </View>
              <Text style={styles.hint}>{tr('languageInSettings')}</Text>
              {message ? <Text style={styles.msg}>{message}</Text> : null}
              <PrimaryButton
                label={tr('createAccount')}
                onPress={() => void onSubmit()}
                loading={loading}
              />
              <PrimaryButton label={tr('back')} onPress={() => setStep(1)} variant="ghost" />
            </>
          ) : null}

          {step === 3 ? (
            <>
              {message ? <Text style={styles.msg}>{message}</Text> : null}
              <PrimaryButton label={tr('login')} onPress={onDone ?? onBack} />
            </>
          ) : null}
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
  step: { color: colors.textDim, fontFamily: fonts.bodyMedium, marginTop: 6, fontSize: 13 },
  sub: { ...typography.subtitle, color: colors.textMuted, marginBottom: spacing.xl, marginTop: 6 },
  label: { color: colors.textMuted, fontFamily: fonts.bodyMedium, marginBottom: 8, marginTop: 4 },
  hint: { color: colors.textDim, fontFamily: fonts.body, fontSize: 13, marginBottom: spacing.md },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: spacing.md },
  chip: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 999,
    paddingHorizontal: 12,
    paddingVertical: 8,
    backgroundColor: colors.bgElevated,
  },
  chipOn: { borderColor: colors.accent, backgroundColor: colors.accentSoft },
  chipText: { color: colors.text, fontFamily: fonts.body, fontSize: 13 },
  msg: { color: colors.textMuted, fontFamily: fonts.body, marginBottom: spacing.md },
});
