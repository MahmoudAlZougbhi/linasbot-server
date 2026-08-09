import { Linking, Modal, Pressable, StyleSheet, Text, View } from 'react-native';

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
    <Modal visible={visible} transparent animationType="fade" onRequestClose={hardLimit ? undefined : onClose}>
      <Pressable
        style={[styles.backdrop, { backgroundColor: colors.overlay }]}
        onPress={hardLimit ? undefined : onClose}
      >
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
            {hardLimit ? 'Keep chatting with Linas AI' : tr('authGateTitle')}
          </Text>
          <Text style={[styles.body, { color: colors.textMuted }]}>
            {reason ||
              (hardLimit
                ? 'You’ve used 10 guest prompts. Sign in to continue with this draft preserved. Guest history stays separate from Owner Copilot memory.'
                : tr('authGateBody'))}
          </Text>
          <PrimaryButton label="Log in with email" onPress={onLogin} />
          <PrimaryButton label="Create account with email" onPress={onRegister} variant="ghost" />
          <View style={styles.legal}>
            <Pressable onPress={() => void Linking.openURL(LEGAL_URLS.privacy)}>
              <Text style={{ color: colors.accent }}>Privacy</Text>
            </Pressable>
            <Text style={{ color: colors.textDim }}> · </Text>
            <Pressable onPress={() => void Linking.openURL(LEGAL_URLS.terms)}>
              <Text style={{ color: colors.accent }}>Terms</Text>
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
              <Text style={{ color: colors.textMuted }}>
                Close without sending — draft stays in the composer
              </Text>
            </Pressable>
          )}
        </Pressable>
      </Pressable>
    </Modal>
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
