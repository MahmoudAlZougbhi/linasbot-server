import { StyleSheet, Text } from 'react-native';

import { PrimaryButton } from '../../components/PrimaryButton';
import { useI18n } from '../../i18n/LanguageContext';
import { colors, fonts, spacing } from '../../theme';
import { AuthChrome } from './AuthChrome';
import { AuthPasswordField } from './AuthFields';

type Props = {
  password: string;
  confirm: string;
  message: string | null;
  loading: boolean;
  onPassword: (v: string) => void;
  onConfirm: (v: string) => void;
  onReset: () => void;
  onBack: () => void;
};

export function ForgotNewPasswordStep({
  password,
  confirm,
  message,
  loading,
  onPassword,
  onConfirm,
  onReset,
  onBack,
}: Props) {
  const { tr } = useI18n();
  return (
    <AuthChrome
      onBack={onBack}
      title={tr('createNewPassword')}
      subtitle={tr('createNewPasswordSub')}
      sparkleSize={52}
    >
      <AuthPasswordField
        autoComplete="new-password"
        placeholder={tr('newPassword')}
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
      <PrimaryButton label={tr('resetPasswordCta')} onPress={onReset} loading={loading} />
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
});
