import { StyleSheet, Text } from 'react-native';

import { PrimaryButton } from '../../components/PrimaryButton';
import { useI18n } from '../../i18n/LanguageContext';
import { colors, fonts, spacing } from '../../theme';
import { AuthChrome } from './AuthChrome';
import { AuthPasswordField, AuthTextField } from './AuthFields';
import { SocialAuthButtons } from './SocialAuthButtons';

type Props = {
  email: string;
  password: string;
  confirm: string;
  message: string | null;
  loading: boolean;
  onEmail: (v: string) => void;
  onPassword: (v: string) => void;
  onConfirm: (v: string) => void;
  onContinue: () => void;
  onBack: () => void;
  onGoLogin: () => void;
  onSocialSuccess: () => void;
  onSocialError: (message: string) => void;
};

export function SignupCredentialsStep({
  email,
  password,
  confirm,
  message,
  loading,
  onEmail,
  onPassword,
  onConfirm,
  onContinue,
  onBack,
  onGoLogin,
  onSocialSuccess,
  onSocialError,
}: Props) {
  const { tr } = useI18n();
  return (
    <AuthChrome
      onBack={onBack}
      progress={1}
      stepLabel={tr('step1of3')}
      title={tr('createAccount')}
      subtitle={tr('registerStepCredentials')}
    >
      <AuthTextField
        autoCapitalize="none"
        keyboardType="email-address"
        autoComplete="email"
        placeholder={tr('email')}
        value={email}
        onChangeText={onEmail}
      />
      <AuthPasswordField
        autoComplete="new-password"
        placeholder={tr('password')}
        value={password}
        onChangeText={onPassword}
      />
      <AuthPasswordField
        autoComplete="new-password"
        placeholder={tr('confirmPassword')}
        value={confirm}
        onChangeText={onConfirm}
      />
      <Text style={styles.hint}>{tr('passwordHint8')}</Text>
      {message ? <Text style={styles.msg}>{message}</Text> : null}
      <PrimaryButton label={tr('continue')} onPress={onContinue} loading={loading} />
      <Text style={styles.switchRow}>
        <Text style={styles.muted}>{tr('alreadyHaveAccount')} </Text>
        <Text style={styles.link} onPress={onGoLogin}>
          {tr('login')}
        </Text>
      </Text>
      <SocialAuthButtons
        onAppleSuccess={onSocialSuccess}
        onAppleError={onSocialError}
        onGoogleSuccess={onSocialSuccess}
        onGoogleError={onSocialError}
      />
    </AuthChrome>
  );
}

const styles = StyleSheet.create({
  hint: {
    color: colors.textDim,
    fontFamily: fonts.body,
    fontSize: 13,
    marginTop: -4,
    marginBottom: spacing.lg,
  },
  msg: { color: colors.danger, fontFamily: fonts.body, marginBottom: spacing.sm },
  switchRow: { textAlign: 'center', marginTop: spacing.lg, marginBottom: spacing.sm, fontSize: 15 },
  muted: { color: colors.textMuted, fontFamily: fonts.body },
  link: { color: colors.accent, fontFamily: fonts.bodyMedium },
});
