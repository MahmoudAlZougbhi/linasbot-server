import { Linking, Pressable, StyleSheet, Text, View } from 'react-native';

import { AppModal } from '../../components/AppModal';
import { ModalScrim } from '../../components/ModalScrim';

import { PrimaryButton } from '../../components/PrimaryButton';
import { LinasStarMark } from '../../components/LinasStarMark';
import { LEGAL_URLS } from '../../config';
import { useI18n } from '../../i18n/LanguageContext';
import { fonts, radii, spacing, useTheme } from '../../theme';

type Props = {
  visible: boolean;
  reason?: string;
  hardLimit?: boolean;
  onClose: () => void;
  onLogin: () => void;
  onRegister: () => void;
};

/** AGT-01 guest gate — preserves draft; hard limit cannot be bypassed by scrim when hardLimit. */
export function AuthGateModal({
  visible,
  reason,
  hardLimit = false,
  onClose,
  onLogin,
  onRegister,
}: Props) {
  const { tr } = useI18n();
  const { colors } = useTheme();

  return (
    <AppModal visible={visible} animationType="fade" onRequestClose={hardLimit ? undefined : onClose}>
      <ModalScrim onPress={hardLimit ? undefined : onClose} justify="flex-end" style={styles.backdrop}>
        <Pressable
          style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}
          onPress={(e) => e.stopPropagation()}
        >
          <View style={styles.top}>
            {!hardLimit ? (
              <Pressable onPress={onClose} accessibilityLabel="Close" hitSlop={8}>
                <Text style={{ color: colors.textMuted, fontSize: 18 }}>✕</Text>
              </Pressable>
            ) : (
              <View style={{ width: 24 }} />
            )}
            <LinasStarMark labeled size={18} />
            <View style={{ width: 24 }} />
          </View>
          <Text style={[styles.title, { color: colors.accentDeep }]}>
            {hardLimit ? tr('authGateHardTitle') : tr('authGateTitle')}
          </Text>
          <Text style={[styles.body, { color: colors.textMuted }]}>
{reason || (hardLimit ? tr('authGateHardBody') : tr('authGateBody'))}
          </Text>
          <PrimaryButton label={tr('authGateLoginEmail')} onPress={onLogin} />
          <PrimaryButton label={tr('authGateRegisterEmail')} onPress={onRegister} variant="ghost" />
          <View style={styles.legal}>
            <Pressable onPress={() => void Linking.openURL(LEGAL_URLS.privacy)}>
              <Text style={{ color: colors.accent }}>{tr('privacy')}</Text>
            </Pressable>
            <Text style={{ color: colors.textDim }}> · </Text>
            <Pressable onPress={() => void Linking.openURL(LEGAL_URLS.terms)}>
              <Text style={{ color: colors.accent }}>{tr('terms')}</Text>
            </Pressable>
          </View>
          {!hardLimit ? (
            <Pressable onPress={onClose} style={styles.later}>
              <Text style={{ color: colors.textMuted, fontFamily: fonts.body }}>
                {tr('continueAsGuest')}
              </Text>
            </Pressable>
          ) : (
            <Pressable onPress={onClose} style={styles.later}>
<Text style={{ color: colors.textMuted }}>{tr('authGateCloseDraft')}</Text>
            </Pressable>
          )}
        </Pressable>
      </ModalScrim>
    </AppModal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    justifyContent: 'flex-end',
    padding: spacing.lg,
  },
  card: {
    borderRadius: radii.xl,
    padding: spacing.xl,
    gap: spacing.md,
    borderWidth: 1,
    marginBottom: spacing.xl,
  },
  top: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  title: {
    fontFamily: fonts.display,
    fontSize: 22,
    textAlign: 'center',
  },
  body: {
    fontFamily: fonts.body,
    fontSize: 15,
    lineHeight: 22,
    textAlign: 'center',
    marginBottom: spacing.sm,
  },
  legal: { flexDirection: 'row', justifyContent: 'center', alignItems: 'center' },
  later: { alignItems: 'center', paddingVertical: spacing.sm },
});
