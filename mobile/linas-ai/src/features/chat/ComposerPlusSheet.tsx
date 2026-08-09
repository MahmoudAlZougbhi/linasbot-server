import { Modal, Pressable, StyleSheet, Text, View } from 'react-native';

import { StatusChip } from '../../components/StatusChip';
import { colors, fonts, radii, spacing } from '../../theme';

export type PlusAction = 'attach_image' | 'attach_video' | 'create_post' | 'add_cm';

type Props = {
  open: boolean;
  onClose: () => void;
  onAction: (action: PlusAction) => void;
};

const ACTIONS: {
  id: PlusAction;
  title: string;
  subtitle: string;
  live: boolean;
}[] = [
  {
    id: 'attach_image',
    title: 'Attach image',
    subtitle: 'Upload coming with media pipeline',
    live: false,
  },
  {
    id: 'attach_video',
    title: 'Attach video',
    subtitle: 'No production video provider yet',
    live: false,
  },
  {
    id: 'create_post',
    title: 'Create post',
    subtitle: 'Open Creative Studio',
    live: true,
  },
  {
    id: 'add_cm',
    title: 'Add CM',
    subtitle: 'Open Content Management',
    live: true,
  },
];

export function ComposerPlusSheet({ open, onClose, onAction }: Props) {
  return (
    <Modal visible={open} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={styles.scrim} onPress={onClose}>
        <Pressable style={styles.sheet} onPress={(e) => e.stopPropagation()}>
          <Text style={styles.title}>Add to chat</Text>
          {ACTIONS.map((a) => (
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
              {!a.live ? <StatusChip label="Coming soon" tone="soon" /> : null}
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
