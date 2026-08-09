import { Modal, Pressable, StyleSheet, Text, View } from 'react-native';

import { useI18n } from '../../i18n/LanguageContext';
import { colors, fonts, radii, spacing } from '../../theme';

export type PlusAction =
  | 'attach_image'
  | 'attach_document'
  | 'add_cm'
  | 'review_setup'
  | 'check_usage';

type Props = {
  open: boolean;
  onClose: () => void;
  onAction: (action: PlusAction) => void;
};

export function ComposerPlusSheet({ open, onClose, onAction }: Props) {
  const { tr } = useI18n();
  const actions: { id: PlusAction; title: string; subtitle: string }[] = [
    { id: 'attach_image', title: tr('attachImage'), subtitle: 'JPEG / PNG / HEIC' },
    { id: 'attach_document', title: tr('attachDocument'), subtitle: 'PDF / images' },
    { id: 'add_cm', title: tr('addEditCm'), subtitle: 'Content Management' },
    { id: 'review_setup', title: tr('reviewSetup'), subtitle: 'CM readiness' },
    { id: 'check_usage', title: tr('checkUsage'), subtitle: 'Credits & wallet' },
  ];

  return (
    <Modal visible={open} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={styles.scrim} onPress={onClose}>
        <Pressable style={styles.sheet} onPress={(e) => e.stopPropagation()}>
          <Text style={styles.title}>{tr('addToChat')}</Text>
          {actions.map((a) => (
            <Pressable
              key={a.id}
              style={styles.row}
              onPress={() => {
                onAction(a.id);
                onClose();
              }}
            >
              <View style={styles.rowText}>
                <Text style={styles.rowTitle}>{a.title}</Text>
                <Text style={styles.rowSub}>{a.subtitle}</Text>
              </View>
            </Pressable>
          ))}
        </Pressable>
      </Pressable>
    </Modal>
  );
}

const styles = StyleSheet.create({
  scrim: {
    flex: 1,
    backgroundColor: colors.overlay,
    justifyContent: 'flex-end',
  },
  sheet: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: radii.xl,
    borderTopRightRadius: radii.xl,
    padding: spacing.xl,
    borderTopWidth: 1,
    borderColor: colors.border,
    gap: spacing.sm,
  },
  title: {
    color: colors.text,
    fontFamily: fonts.display,
    fontSize: 18,
    marginBottom: spacing.sm,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: colors.bgElevated,
    borderRadius: radii.md,
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: colors.borderSoft,
  },
  rowText: { flex: 1, paddingRight: 8 },
  rowTitle: { color: colors.text, fontFamily: fonts.bodyMedium, fontSize: 16 },
  rowSub: { color: colors.textMuted, fontFamily: fonts.body, fontSize: 12, marginTop: 2 },
});
