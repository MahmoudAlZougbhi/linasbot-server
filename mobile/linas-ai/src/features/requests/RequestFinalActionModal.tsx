import { Modal, StyleSheet, Text, View } from 'react-native';

import { PrimaryButton } from '../../components/PrimaryButton';
import { TextField } from '../../components/TextField';
import { useI18n } from '../../i18n/LanguageContext';
import { fonts, radii, spacing, useTheme } from '../../theme';

type Props = {
  visible: boolean;
  title: string;
  message: string;
  busy: boolean;
  onChangeMessage: (v: string) => void;
  onConfirm: () => void;
  onCancel: () => void;
};

export function RequestFinalActionModal({
  visible,
  title,
  message,
  busy,
  onChangeMessage,
  onConfirm,
  onCancel,
}: Props) {
  const { colors } = useTheme();
  const { tr } = useI18n();

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onCancel}>
      <View style={[styles.backdrop, { backgroundColor: colors.overlay }]}>
        <View style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}>
          <Text style={[styles.title, { color: colors.text }]}>{title}</Text>
          <Text style={[styles.hint, { color: colors.textMuted }]}>{tr('reqFinalMessageHint')}</Text>
          <Text style={[styles.label, { color: colors.textMuted }]}>{tr('reqFinalMessageLabel')}</Text>
          <TextField
            value={message}
            onChangeText={onChangeMessage}
            multiline
            editable={!busy}
            accessibilityLabel={tr('reqFinalMessageLabel')}
          />
          <PrimaryButton
            label={busy ? tr('reqActionBusy') : tr('reqFinalConfirm')}
            onPress={onConfirm}
            loading={busy}
            disabled={busy}
          />
          <PrimaryButton
            label={tr('reqFinalCancel')}
            onPress={onCancel}
            variant="ghost"
            disabled={busy}
            style={styles.cancel}
          />
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    justifyContent: 'center',
    padding: spacing.xl,
  },
  card: {
    borderWidth: 1,
    borderRadius: radii.lg,
    padding: spacing.xl,
  },
  title: { fontFamily: fonts.bodyMedium, fontSize: 18, marginBottom: spacing.sm },
  hint: { fontFamily: fonts.body, fontSize: 13, marginBottom: spacing.md },
  label: { fontFamily: fonts.body, fontSize: 12, marginBottom: spacing.xs },
  cancel: { marginTop: spacing.sm },
});
