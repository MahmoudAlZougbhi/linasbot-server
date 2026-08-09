import { Modal, Pressable, StyleSheet, Text, View } from 'react-native';

import { StatusChip } from '../../components/StatusChip';
import { useI18n } from '../../i18n/LanguageContext';
import { colors, fonts, radii, spacing } from '../../theme';

export type PlusAction =
  | 'attach_image'
  | 'attach_video'
  | 'create_post'
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
  const actions: {
    id: PlusAction;
    title: string;
    subtitle: string;
    live: boolean;
  }[] = [
    {
      id: 'create_post',
      title: tr('createPost'),
      subtitle: 'Creative Studio',
      live: true,
    },
    {
      id: 'add_cm',
      title: tr('addEditCm'),
      subtitle: 'Content Management',
      live: true,
    },
    {
      id: 'review_setup',
      title: tr('reviewSetup'),
      subtitle: 'CM readiness',
      live: true,
    },
    {
      id: 'check_usage',
      title: tr('checkUsage'),
      subtitle: 'Credits & wallet',
      live: true,
    },
    {
      id: 'attach_image',
      title: tr('attachImage'),
      subtitle: tr('attachSoon'),
      live: false,
    },
    {
      id: 'attach_video',
      title: tr('attachVideo'),
      subtitle: tr('attachSoon'),
      live: false,
    },
  ];

  return (
    <Modal visible={open} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={styles.scrim} onPress={onClose}>
        <Pressable style={styles.sheet} onPress={(e) => e.stopPropagation()}>
          <Text style={styles.title}>{tr('addToChat')}</Text>
          {actions.map((a) => (
            <Pressable
              key={a.id}
              style={[styles.row, !a.live && styles.rowDisabled]}
              disabled={!a.live}
              onPress={() => {
                onAction(a.id);
                onClose();
              }}
            >
              <View style={styles.rowText}>
                <Text style={styles.rowTitle}>{a.title}</Text>
                <Text style={styles.rowSub}>{a.subtitle}</Text>
              </View>
              {!a.live ? <StatusChip label={tr('comingSoon')} tone="soon" /> : null}
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
  rowDisabled: { opacity: 0.7 },
  rowText: { flex: 1, paddingRight: 8 },
  rowTitle: { color: colors.text, fontFamily: fonts.bodyMedium, fontSize: 16 },
  rowSub: { color: colors.textMuted, fontFamily: fonts.body, fontSize: 12, marginTop: 2 },
});
