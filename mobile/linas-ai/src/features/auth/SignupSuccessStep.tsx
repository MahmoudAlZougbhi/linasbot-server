import { StyleSheet, Text, View } from 'react-native';

import { AppIcon, feather } from '../../components/AppIcon';
import { PrimaryButton } from '../../components/PrimaryButton';
import { useI18n } from '../../i18n/LanguageContext';
import { colors, fonts, spacing, typography } from '../../theme';
import { AuthChrome } from './AuthChrome';

type Props = {
  onContinue: () => void;
};

export function SignupSuccessStep({ onContinue }: Props) {
  const { tr } = useI18n();
  return (
    <AuthChrome title={tr('youreAllSet')} subtitle={tr('accountReady')} sparkleSize={52}>
      <View style={styles.checkWrap}>
        <View style={styles.checkCircle}>
          <AppIcon icon={feather('check')} size={22} color={colors.accent} />
        </View>
      </View>
      <View style={styles.spacer} />
      <PrimaryButton label={tr('continueToLinas')} onPress={onContinue} />
      <Text style={styles.pad} />
    </AuthChrome>
  );
}

const styles = StyleSheet.create({
  checkWrap: { alignItems: 'center', marginTop: spacing.md, marginBottom: spacing.xl },
  checkCircle: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: colors.mintSoft,
    alignItems: 'center',
    justifyContent: 'center',
  },
  spacer: { flex: 1, minHeight: 48 },
  pad: { ...typography.caption, color: colors.textDim, fontFamily: fonts.body, height: 8 },
});
