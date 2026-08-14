import { Pressable, StyleSheet, Text, View } from 'react-native';

import { AppIcon, feather } from '../../components/AppIcon';
import { PrimaryButton } from '../../components/PrimaryButton';
import { useI18n } from '../../i18n/LanguageContext';
import { colors, fonts, radii, spacing } from '../../theme';
import { AuthChrome } from './AuthChrome';

export type AddressGender = 'male' | 'female' | 'unset';

type Props = {
  gender: AddressGender;
  message: string | null;
  loading: boolean;
  onGender: (g: AddressGender) => void;
  onFinish: () => void;
  onBack: () => void;
};

const OPTIONS: Array<{ value: AddressGender; key: 'genderMale' | 'genderFemale' | 'genderUnset' }> = [
  { value: 'male', key: 'genderMale' },
  { value: 'female', key: 'genderFemale' },
  { value: 'unset', key: 'genderUnset' },
];

export function SignupAddressStep({ gender, message, loading, onGender, onFinish, onBack }: Props) {
  const { tr } = useI18n();
  return (
    <AuthChrome
      onBack={onBack}
      progress={3}
      stepLabel={tr('step3of3')}
      title={tr('howShouldLinasAddress')}
      subtitle={tr('addressYouSub')}
    >
      {OPTIONS.map((opt) => {
        const on = gender === opt.value;
        return (
          <Pressable
            key={opt.value}
            onPress={() => onGender(opt.value)}
            style={[styles.card, on && styles.cardOn]}
            accessibilityRole="radio"
            accessibilityState={{ selected: on }}
          >
            <AppIcon icon={feather('user')} size={22} color={on ? colors.accent : colors.textMuted} />
            <Text style={styles.cardLabel}>{tr(opt.key)}</Text>
            <View style={[styles.radio, on && styles.radioOn]}>
              {on ? <View style={styles.radioDot} /> : null}
            </View>
          </Pressable>
        );
      })}
      {message ? <Text style={styles.msg}>{message}</Text> : null}
      <View style={styles.spacer} />
      <PrimaryButton label={tr('finish')} onPress={onFinish} loading={loading} />
    </AuthChrome>
  );
}

const styles = StyleSheet.create({
  card: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: 16,
    marginBottom: spacing.md,
    backgroundColor: colors.surface,
  },
  cardOn: {
    borderColor: colors.accent,
    backgroundColor: colors.mintSoft,
  },
  cardLabel: { flex: 1, color: colors.text, fontFamily: fonts.bodyMedium, fontSize: 16 },
  radio: {
    width: 22,
    height: 22,
    borderRadius: 11,
    borderWidth: 1.5,
    borderColor: colors.border,
    alignItems: 'center',
    justifyContent: 'center',
  },
  radioOn: { borderColor: colors.accent },
  radioDot: {
    width: 12,
    height: 12,
    borderRadius: 6,
    backgroundColor: colors.accent,
  },
  spacer: { flex: 1, minHeight: 24 },
  msg: { color: colors.danger, fontFamily: fonts.body, marginBottom: spacing.sm },
});
