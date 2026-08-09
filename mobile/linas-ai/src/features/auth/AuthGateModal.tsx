import { Modal, Pressable, StyleSheet, Text, View } from 'react-native';

import { PrimaryButton } from '../../components/PrimaryButton';
import { useI18n } from '../../i18n/LanguageContext';
import { colors, fonts, radii, spacing, typography } from '../../theme';
import { LinasAvatar } from '../linas/LinasAvatar';

type Props = {
  visible: boolean;
  reason?: string;
  onClose: () => void;
  onLogin: () => void;
  onRegister: () => void;
};

export function AuthGateModal({ visible, reason, onClose, onLogin, onRegister }: Props) {
  const { tr } = useI18n();
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={styles.backdrop} onPress={onClose}>
        <Pressable style={styles.card} onPress={(e) => e.stopPropagation()}>
          <LinasAvatar state="helping" size={72} />
          <Text style={styles.title}>{tr('authGateTitle')}</Text>
          <Text style={styles.body}>{reason || tr('authGateBody')}</Text>
          <PrimaryButton label={tr('login')} onPress={onLogin} />
          <PrimaryButton label={tr('createAccount')} onPress={onRegister} variant="ghost" />
          <Pressable onPress={onClose} style={styles.later}>
            <Text style={styles.laterText}>{tr('continueAsGuest')}</Text>
          </Pressable>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: colors.overlay,
    justifyContent: 'center',
    padding: spacing.xl,
  },
  card: {
    backgroundColor: colors.surface,
    borderRadius: radii.xl,
    padding: spacing.xl,
    gap: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: 'center',
  },
  title: {
    ...typography.title,
    color: colors.accentDeep,
    fontSize: 22,
    marginTop: spacing.sm,
    textAlign: 'center',
  },
  body: {
    ...typography.subtitle,
    color: colors.textMuted,
    marginBottom: spacing.sm,
    textAlign: 'center',
  },
  later: { alignItems: 'center', paddingVertical: spacing.sm },
  laterText: { color: colors.textMuted, fontFamily: fonts.body, fontSize: 14 },
});
