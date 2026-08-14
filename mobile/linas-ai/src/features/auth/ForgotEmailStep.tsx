import { StyleSheet, Text } from 'react-native';

import { PrimaryButton } from '../../components/PrimaryButton';
import { useI18n } from '../../i18n/LanguageContext';
import { colors, fonts, spacing } from '../../theme';
import { AuthChrome } from './AuthChrome';
import { AuthTextField } from './AuthFields';

type Props = {
  email: string;
  message: string | null;
  loading: boolean;
  onEmail: (v: string) => void;
  onSend: () => void;
  onBack: () => void;
};

export function ForgotEmailStep({ email, message, loading, onEmail, onSend, onBack }: Props) {
  const { tr } = useI18n();
  return (
    <AuthChrome
      onBack={onBack}
      title={tr('forgotPasswordTitle')}
      subtitle={tr('forgotPasswordSub')}
      sparkleSize={52}
      footer={
        <Text style={styles.switchRow}>
          <Text style={styles.muted}>{tr('rememberPassword')} </Text>
          <Text style={styles.link} onPress={onBack}>
            {tr('login')}
          </Text>
        </Text>
      }
    >
      <AuthTextField
        autoCapitalize="none"
        keyboardType="email-address"
        autoComplete="email"
        placeholder={tr('email')}
        value={email}
        onChangeText={onEmail}
      />
      {message ? <Text style={styles.msg}>{message}</Text> : null}
      <PrimaryButton label={tr('sendResetCode')} onPress={onSend} loading={loading} />
    </AuthChrome>
  );
}

const styles = StyleSheet.create({
  msg: { color: colors.danger, fontFamily: fonts.body, marginBottom: spacing.sm },
  switchRow: { textAlign: 'center', fontSize: 15 },
  muted: { color: colors.text, fontFamily: fonts.body },
  link: { color: colors.accent, fontFamily: fonts.bodyMedium },
});
