import { Pressable, StyleSheet, Text } from 'react-native';

import { PrimaryButton } from '../../components/PrimaryButton';
import { useI18n } from '../../i18n/LanguageContext';
import { colors, fonts, spacing } from '../../theme';
import { AuthChrome } from './AuthChrome';
import { AuthOtpRow } from './AuthOtpRow';
import { maskEmail } from './maskEmail';

type Props = {
  email: string;
  code: string;
  message: string | null;
  loading: boolean;
  onCode: (v: string) => void;
  onContinue: () => void;
  onResend: () => void;
  onChangeEmail: () => void;
  onBack: () => void;
};

export function ForgotCodeStep({
  email,
  code,
  message,
  loading,
  onCode,
  onContinue,
  onResend,
  onChangeEmail,
  onBack,
}: Props) {
  const { tr } = useI18n();
  return (
    <AuthChrome
      onBack={onBack}
      title={tr('checkYourEmail')}
      subtitle={`${tr('enter6DigitSentTo')}\n${maskEmail(email)}`}
      sparkleSize={52}
    >
      <AuthOtpRow value={code} onChange={onCode} />
      {message ? <Text style={styles.msg}>{message}</Text> : null}
      <PrimaryButton label={tr('continue')} onPress={onContinue} loading={loading} />
      <Text style={styles.resendRow}>
        <Text style={styles.muted}>{tr('didntGetCode')} </Text>
        <Text style={styles.link} onPress={onResend}>
          {tr('resend')}
        </Text>
      </Text>
      <Pressable onPress={onChangeEmail} style={styles.change}>
        <Text style={styles.link}>{tr('changeEmail')}</Text>
      </Pressable>
    </AuthChrome>
  );
}

const styles = StyleSheet.create({
  msg: { color: colors.danger, fontFamily: fonts.body, marginBottom: spacing.sm },
  resendRow: { textAlign: 'center', marginTop: spacing.lg, fontSize: 15 },
  muted: { color: colors.text, fontFamily: fonts.body },
  link: { color: colors.accent, fontFamily: fonts.bodyMedium },
  change: { alignItems: 'center', marginTop: spacing.md },
});
